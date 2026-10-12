import json
import logging
import os
import re as _re
import time
from datetime import datetime
from typing import Any

from app.models.db import Exercise, Resource, User
from app.processing.ai_client import AIClient
from app.processing.embeddings import retrieve_relevant_chunks
from app.processing.note_processor import get_pipeline_for_user
from app.processing.ocr import OCRProcessor
from app.schemas.exercise import GradeResponse
from app.utils.db import SessionLocal
from app.utils.storage import StorageManager
from app.utils.tasks import TaskManager

logger = logging.getLogger(__name__)


def _run_async(coro_fn, *args, **kwargs):
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: asyncio.run(coro_fn(*args, **kwargs)))
            return future.result()
    else:
        return asyncio.run(coro_fn(*args, **kwargs))


def _looks_like_provider_error(raw_response: str) -> bool:
    if not raw_response:
        return False
    lower = raw_response.strip().lower()
    error_markers = [
        "connection failed",
        "failed after",
        "provider error",
        "timeout",
        "timed out",
        "[gemini]",
        "[huggingface]",
        "[ollama]",
    ]
    return any(marker in lower for marker in error_markers)


def _normalize_type(raw: str) -> str:
    lower = (raw or "").lower()
    if lower in {"objective", "multiple_choice", "multiple-choice", "mcq"}:
        return "objective"
    if lower in {"fill_in_the_blank", "fill-in-the-blank", "blank"}:
        return "fill_in_the_blank"
    return "subjective"


def _try_parse_import_payload(raw_response: str):
    if not raw_response:
        raise json.JSONDecodeError("Empty response", "", 0)
    candidates = []
    text = raw_response.strip()
    candidates.append(text)
    fenced_blocks = _re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=_re.IGNORECASE)
    candidates.extend([block.strip() for block in fenced_blocks if block.strip()])
    obj_end = text.rfind("}")
    if obj_end != -1:
        start = text.find("{")
        while start != -1 and start < obj_end:
            candidates.append(text[start : obj_end + 1].strip())
            start = text.find("{", start + 1)
            
    arr_end = text.rfind("]")
    if arr_end != -1:
        start = text.find("[")
        while start != -1 and start < arr_end:
            candidates.append(text[start : arr_end + 1].strip())
            start = text.find("[", start + 1)
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("Could not parse JSON payload", text, 0)


def _extract_fallback_questions(raw_text: str) -> list[dict[str, Any]]:
    if not raw_text:
        return []
    extracted: list[dict[str, Any]] = []
    qa_pattern = _re.compile(
        r"(?ims)(?:^|\n)\s*(?:#*\s*q(?:uestion)?\s*[\d.\-)]*[\s:\-]*)\n*(.+?)\s*"
        r"(?:\n|\r\n)\s*(?:#*\s*(?:j(?:awapan)?\s*/?\s*)?a(?:nswer)?\s*[\d.\-)]*[\s:\-]*)\n*(.+?)"
        r"(?=\n\s*(?:#*\s*q(?:uestion)?\s*[\d.\-)]*[\s:\-])|\Z)"
    )
    for match in qa_pattern.finditer(raw_text):
        q_text = " ".join(match.group(1).split())
        a_text = " ".join(match.group(2).split())
        if not q_text:
            continue
        q_type = "fill_in_the_blank" if "_____" in q_text else "subjective"
        extracted.append(
            {
                "question_text": q_text,
                "original_number": None,
                "answer_text": a_text,
                "question_type": q_type,
                "options": None,
            }
        )
    if extracted:
        return extracted

    lines = [line.strip() for line in raw_text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        question_text = None
        q_match = _re.match(
            r"^(?:q(?:uestion)?\s*[\d.\-)]*\s*[:\-]\s*)?(.*\?)$", line, flags=_re.IGNORECASE
        )
        if q_match:
            question_text = q_match.group(1).strip()
        if not question_text:
            i += 1
            continue
        answer_parts: list[str] = []
        j = i + 1
        while j < len(lines):
            candidate = lines[j]
            if not candidate:
                if answer_parts:
                    break
                j += 1
                continue
            if candidate.endswith("?"):
                break
            candidate = _re.sub(r"^(?:a(?:nswer)?\s*[:\-]\s*)", "", candidate, flags=_re.IGNORECASE)
            answer_parts.append(candidate)
            j += 1
        answer_text = " ".join(answer_parts).strip() or "Answer not provided in source text."
        q_type = "fill_in_the_blank" if "_____" in question_text else "subjective"
        extracted.append(
            {
                "question_text": question_text,
                "original_number": None,
                "answer_text": answer_text,
                "question_type": q_type,
                "options": None,
            }
        )
        i = j if j > i else i + 1
    return extracted


def _normalize_question_structure(q: dict) -> dict:
    """Validate and normalize marks, sub_parts, marking_scheme on a question dict."""
    q["max_marks"] = max(int(q.get("max_marks", 0) or 0), 0)

    raw_scheme = q.get("marking_scheme", [])
    if isinstance(raw_scheme, list):
        normalized_scheme = []
        for c in raw_scheme:
            if isinstance(c, dict):
                normalized_scheme.append({
                    "criterion": str(c.get("criterion", c.get("name", ""))),
                    "max_points": int(c.get("max_points", c.get("marks", 1)) or 1),
                    "description": str(c.get("description", "")),
                })
        q["marking_scheme"] = normalized_scheme
    else:
        q["marking_scheme"] = []

    raw_sub_parts = q.get("sub_parts", [])
    if isinstance(raw_sub_parts, list):
        q["sub_parts"] = _normalize_sub_parts(raw_sub_parts, q.get("id", ""))
    else:
        q["sub_parts"] = []

    if q["sub_parts"]:
        child_sum = sum(sp.get("max_marks", 0) for sp in q["sub_parts"])
        if child_sum > 0 and q["max_marks"] == 0:
            q["max_marks"] = child_sum

    if q["max_marks"] == 0:
        q["max_marks"] = 1

    # If the AI produced no marking scheme for a subjective/fill_in_blank question,
    # synthesise a single fallback criterion so grading always has a structured scheme.
    q_type = str(q.get("question_type", "subjective"))
    if not q["marking_scheme"] and q_type not in {"objective", "multiple_choice", "mcq"}:
        q["marking_scheme"] = [
            {
                "criterion": "Overall correctness",
                "max_points": q["max_marks"],
                "description": "Award marks based on accuracy and completeness of the answer.",
            }
        ]

    return q


def _normalize_sub_parts(parts: list, parent_id: str, depth: int = 0) -> list:
    """Recursively normalize sub-parts with depth limit of 3."""
    if depth >= 3:
        return []
    normalized = []
    for i, sp in enumerate(parts):
        if not isinstance(sp, dict):
            continue
        label = str(sp.get("label", chr(97 + i)))
        sp["id"] = str(sp.get("id", f"{parent_id}{label}"))
        sp["label"] = label
        sp["question_text"] = str(sp.get("question_text", "") or "")
        sp["answer_text"] = str(sp.get("answer_text", "") or "")
        sp["max_marks"] = max(int(sp.get("max_marks", 0) or 0), 0)
        sp["question_type"] = str(sp.get("question_type", "subjective"))
        sp["options"] = sp.get("options") if sp.get("question_type") == "objective" else None
        sp["order"] = int(sp.get("order", i))

        raw_scheme = sp.get("marking_scheme", [])
        if isinstance(raw_scheme, list):
            sp["marking_scheme"] = [
                {
                    "criterion": str(c.get("criterion", c.get("name", ""))),
                    "max_points": int(c.get("max_points", c.get("marks", 1)) or 1),
                    "description": str(c.get("description", "")),
                }
                for c in raw_scheme if isinstance(c, dict)
            ]
        else:
            sp["marking_scheme"] = []

        sp["sub_parts"] = _normalize_sub_parts(
            sp.get("sub_parts") or [], sp["id"], depth + 1
        )

        if sp["sub_parts"]:
            child_sum = sum(s.get("max_marks", 0) for s in sp["sub_parts"])
            if child_sum > 0 and sp["max_marks"] == 0:
                sp["max_marks"] = child_sum
        if sp["max_marks"] == 0:
            sp["max_marks"] = 1

        normalized.append(sp)
    return normalized


def _extract_title_from_text(raw_text: str) -> str | None:
    if not raw_text:
        return None
    question_words = {
        "what",
        "how",
        "why",
        "when",
        "which",
        "where",
        "who",
        "define",
        "explain",
        "list",
        "name",
        "describe",
        "is",
        "are",
        "does",
        "do",
        "can",
        "would",
        "could",
        "should",
    }
    lines = raw_text.strip().split("\n")
    best = None
    for line in lines:
        stripped = line.strip().strip("# \t")
        if not stripped or len(stripped) < 4:
            continue
        if stripped.isdigit():
            continue
        # Skip markdown image/link syntax (e.g. ![Figure](...) or [text](...))
        if stripped.startswith("![") or stripped.startswith("["):
            continue
        # Skip lines that are mostly a URL or file path
        if stripped.startswith("http") or stripped.startswith("/"):
            continue
        first_word = stripped.split()[0].lower().strip("()[].,:;!?")
        if stripped.endswith("?"):
            continue
        if first_word in question_words:
            continue
        if 10 <= len(stripped) <= 80:
            best = stripped
        elif best is None and len(stripped) < 100:
            best = stripped
    return best


def process_exercise_task(exercise_id: str, user_id: int, task_id: str | None = None, **kwargs):
    db = SessionLocal()
    try:
        exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
        user = db.query(User).filter(User.id == user_id).first()

        if not exercise or not user:
            if task_id:
                TaskManager._update_db_task(
                    task_id, status="failed", error="Exercise or User not found"
                )
            return

        def progress_callback(percent, message=None):
            if task_id:
                TaskManager.update_task_progress(task_id, percent, message=message)

        start_time = time.time()
        file_path = exercise.file_path
        file_ext = os.path.splitext(file_path)[1].lower() if file_path else ""

        progress_callback(10, "Extracting text from file...")
        raw_text = ""

        try:
            from app.processing.unified_processor import UnifiedContentProcessor

            processor = UnifiedContentProcessor(use_polish=False)
            bundle = processor.extract(file_path, resource_id=exercise_id)
            raw_text = bundle.markdown

            if bundle.images and exercise_id:
                images_data = [
                    img.to_dict() if hasattr(img, "to_dict") else img for img in bundle.images
                ]
                from app.utils.storage import StorageManager

                StorageManager.save_resource_json(exercise_id, "images", images_data)
                StorageManager.save_resource_json(exercise_id, "image_map", bundle.image_map)
        except ImportError:
            if file_ext in (".pdf", ".pptx", ".ppt", ".txt", ".md", ".docx"):
                if file_ext == ".docx":
                    from docx import Document

                    doc = Document(file_path)
                    raw_text = "\n".join([p.text for p in doc.paragraphs])
                else:
                    pipeline = get_pipeline_for_user(user)
                    pipeline.use_polish = False
                    raw_text = pipeline.process(file_path)
                    if isinstance(raw_text, str) and raw_text.startswith("Error:"):
                        raise RuntimeError(raw_text)
            else:
                ocr_result = OCRProcessor.extract_text(
                    file_path,
                    "image" if file_ext in (".png", ".jpg", ".jpeg") else "unknown",
                    note_id=exercise_id,
                )
                raw_text = ocr_result.get("raw_text", "")

        if not raw_text.strip():
            raise ValueError("No text could be extracted from the file.")

        progress_callback(30, "Loading subject resources...")

        subject_resources = (
            db.query(Resource.id, Resource.title)
            .filter(Resource.subject_id == exercise.subject_id, Resource.user_id == user_id)
            .all()
        )
        resource_titles = [(r.id, r.title) for r in subject_resources]
        title_to_id = {title.strip(): rid for rid, title in resource_titles if title}

        if title_to_id:
            resource_context = "The following resources exist in this subject. For each extracted question, identify which resource it likely references:\n"
            for rid, rtitle in resource_titles:
                resource_context += f"- {rtitle}\n"
        else:
            resource_context = ""

        progress_callback(40, "Using AI to parse questions and answers...")

        text = raw_text
        # Groq free tier hard limit: 6,000 TPM (input+output tokens combined).
        # The exercise extraction prompt template is ~3,500 tokens of overhead.
        # To stay under 6,000 TPM we can only fit ~2,500 tokens of text (~4,000 chars).
        # Cap tightly so Groq (Tier1) doesn't get a 413; Gemini (Tier2) handles the full text.
        GROQ_SAFE_CHARS = 4000
        if len(text) > 25000:
            text = text[:25000] + "... [truncated]"

        text = _re.sub(r"(?<=[.!?])\s+(?=[b-z]\.\s)", "\n", text)
        text = _re.sub(r"(?<=\.)\s+(?=\([b-z]\)\s)", "\n", text)


        def _build_prompt(body_text: str) -> str:
            return f"""Extract and structure all quiz questions from the following text.
Text to process:
---
{body_text}
---

{resource_context}
Rules:
1. **Identify Questions and Answers**: Pair each question with its corresponding answer. Questions often follow headers like "# QUESTION 1", and answers often follow headers like "## Jawapan / Answer".
2. **STRICTLY ENGLISH ONLY**: The text contains questions in BOTH Malay and English (e.g., "Dua hubungan..." followed by "Two relations..."). You MUST extract **ONLY the English questions and answers**. DO NOT include the Malay text in your output under any circumstances. Ignore all Malay translations completely.
3. **Generate Missing Answers**: If 'generate_missing_answers' is true, generate accurate answers for any questions that are missing them, based on context.
4. **CRITICAL - Rejoin Broken Lines**: The input may be from a PDF or scanned document where sentences are broken mid-line. Rejoin them into complete, coherent sentences.
5. **CRITICAL - Math & Matrices Formatting**: Preserve all mathematical symbols, equations, superscripts, and subscripts exactly (e.g. `n^2 + n`, `R1 ∪ R2`). For matrices and multi-line equations, use explicit newline characters (`\\n`) within the string. NEVER flatten matrices or multi-line definitions into a single line.
6. **CRITICAL - Image Preservation**: The source text may contain markdown image tags like `![image_0](...)`. You MUST preserve these exact tags inline within the `question_text` or `answer_text` exactly where they appear. DO NOT remove or modify them.
7. **CRITICAL - No Orphaned Words**: Never leave a word or abbreviation stranded alone at the end of a sentence.
8. **CRITICAL - Clean Question Clusters**: Extract the real question text that follows headers and only use the first number as the `original_number`.
9. **CRITICAL - Remove Non-Content**: Strip out page numbers, chapter titles, etc. (But DO NOT strip out image tags).
10. **NO Empty Strings**: Never include empty strings.
11. **CRITICAL - Handle Squished Lists**: Split them onto SEPARATE LINES with `\\n`, keeping the original letter prefix. NEVER convert `a. / b. / c.` markers to `- `.
12. **Nested Inline Lists**: Convert inline lists to numbered lines.
13. **Question Extraction**: The `original_number` is the question label. The `question_text` must NOT start with the original number.
14. **Marks Detection**: Detect marks/points for each question from patterns like "(4 marks)", "[4]", "4 points", "total: 5". If a question has labeled sub-parts (a, b, c or i, ii, iii), split them into `sub_parts`.
15. **Format the output as a strict JSON object**. The JSON object must have:
    - `"suggested_title"`: A short, descriptive title.
    - `"questions"`: An array of objects, each with:
        - `"question_text"`: Clean question text (no leading number). Must include `\\n` for multi-line content. Must retain `![image...](...)` if present.
        - `"original_number"`: The original question label (e.g., "1.1"). `null` if not found.
        - `"answer_text"`: The answer. Must include `\\n` for multi-line content. Must retain `![image...](...)` if present.
        - `"question_type"`: One of `"objective"`, `"subjective"`, `"fill_in_the_blank"`.
        - `"options"`: For `"objective"`, an array of 4 options. `null` for others.
        - `"topic"`: A short 1-4 word description of the specific topic or concept this question covers.
        - `"difficulty"`: Must be "Easy", "Medium", or "Hard".
        - `"max_marks"`: Total marks available for this question (integer). Default to 1 if not found.
        - `"sub_parts"`: Array of sub-questions if the question has labeled parts (a, b, c or i, ii, iii). Each with:
            - `"label"`: The letter/number prefix (e.g., "a", "b", "i", "ii").
            - `"question_text"`: The sub-part question text.
            - `"answer_text"`: The sub-part answer.
            - `"max_marks"`: Marks for this sub-part.
            - `"sub_parts"`: Nested sub-parts (for 3-level like 1a(i)).
            - `"question_type"`: Same classification as parent.
            - `"options"`: For objective sub-parts.
        - `"marking_scheme"`: Array of marking criteria, each with:
            - `"criterion"`: Short name (e.g., "Correct formula")
            - `"max_points"`: Points allocated for this criterion
            - `"description"`: What the student must demonstrate
        - `"resource_title"`: The exact title of the resource (from the list above) that this question likely references. `null` if unclear.
        - `"reference_quote"`: A short excerpt from the extracted text (not from the resource list) that supports the answer. `null` if none.

Generate_missing_answers: True
Respond with ONLY the JSON object.
"""

        # Pass 1: Try Groq-safe truncated text (avoids 413 TPM error on free tier).
        # Groq limit is 6,000 TPM (input+output). Prompt overhead is ~3,500 tokens,
        # leaving ~2,500 tokens for text content (~4,000 chars).
        groq_text = text[:GROQ_SAFE_CHARS] + ("... [truncated]" if len(text) > GROQ_SAFE_CHARS else "")
        prompt = _build_prompt(groq_text)

        client = AIClient(category="processing")
        response = _run_async(
            client.generate_text,
            prompt=prompt,
            system_instruction="You are an expert educational content extractor.",
            max_tokens=8192,
            require_reasoning=False,
            raw_output=True,
        )

        provider_failed = _looks_like_provider_error(response)
        suggested_title = None
        questions_data = []

        if not provider_failed:
            try:
                data = _try_parse_import_payload(response)
                if isinstance(data, list):
                    questions_data = data
                else:
                    questions_data = data.get("questions", [])
                    raw_title = data.get("suggested_title")
                    suggested_title = (
                        raw_title.strip()
                        if isinstance(raw_title, str) and raw_title.strip()
                        else None
                    )
            except json.JSONDecodeError:
                logger.error(f"Failed to parse imported quiz JSON: {response}")

        if not questions_data:
            questions_data = _extract_fallback_questions(text)

        still_has_filename_title = (
            exercise.file_name and exercise.title == os.path.splitext(exercise.file_name)[0]
        )
        if still_has_filename_title:
            if suggested_title:
                cleaned = suggested_title.strip().strip("# \t")
                if cleaned and not cleaned.isdigit() and len(cleaned) >= 3:
                    exercise.title = cleaned
            if (
                exercise.title == os.path.splitext(exercise.file_name or "")[0]
                or len(exercise.title) < 3
                or exercise.title.isdigit()
            ):
                extracted = _extract_title_from_text(raw_text)
                if extracted:
                    exercise.title = extracted
            db.commit()

        if not questions_data:
            raise ValueError("AI failed to structure the imported content properly.")

        normalized_questions = []
        for q_data in questions_data:
            if not isinstance(q_data, dict):
                continue
            q_text = str(q_data.get("question_text") or q_data.get("question") or "").strip()
            if not q_text:
                continue
            q_type = _normalize_type(str(q_data.get("question_type") or q_data.get("type") or "subjective"))
            options = q_data.get("options") if q_type == "objective" else None

            r_title = q_data.get("resource_title") or ""
            r_title_clean = r_title.strip() if r_title else ""
            mapped_id = None
            if r_title_clean and title_to_id:
                mapped_id = title_to_id.get(r_title_clean)
                if not mapped_id:
                    for t, rid in title_to_id.items():
                        if t.lower() in r_title_clean.lower() or r_title_clean.lower() in t.lower():
                            mapped_id = rid
                            break

            q_data = _normalize_question_structure(q_data)

            normalized_questions.append(
                {
                    "question_text": q_text,
                    "original_number": q_data.get("original_number"),
                    "answer_text": str(q_data.get("answer_text") or q_data.get("answer") or "").strip(),
                    "question_type": q_type,
                    "options": options,
                    "topic": q_data.get("topic"),
                    "difficulty": q_data.get("difficulty"),
                    "max_marks": q_data.get("max_marks", 1),
                    "sub_parts": q_data.get("sub_parts", []),
                    "marking_scheme": q_data.get("marking_scheme", []),
                    "reference_resource_id": mapped_id,
                    "reference_resource_title": r_title_clean if r_title_clean else None,
                    "reference_quote": q_data.get("reference_quote"),
                }
            )

        if not normalized_questions:
            questions_data = _extract_fallback_questions(text)
            for q_data in questions_data:
                if not isinstance(q_data, dict):
                    continue
                q_text = str(q_data.get("question_text") or q_data.get("question") or "").strip()
                if not q_text:
                    continue
                q_type = _normalize_type(str(q_data.get("question_type") or q_data.get("type") or "subjective"))
                options = q_data.get("options") if q_type == "objective" else None

                r_title = q_data.get("resource_title") or ""
                r_title_clean = r_title.strip() if r_title else ""
                mapped_id = None
                if r_title_clean and title_to_id:
                    mapped_id = title_to_id.get(r_title_clean)
                    if not mapped_id:
                        for t, rid in title_to_id.items():
                            if t.lower() in r_title_clean.lower() or r_title_clean.lower() in t.lower():
                                mapped_id = rid
                                break

                q_data = _normalize_question_structure(q_data)

                normalized_questions.append(
                    {
                        "question_text": q_text,
                        "original_number": q_data.get("original_number"),
                        "answer_text": str(q_data.get("answer_text") or q_data.get("answer") or "").strip(),
                        "question_type": q_type,
                        "options": options,
                        "topic": q_data.get("topic"),
                        "difficulty": q_data.get("difficulty"),
                        "max_marks": q_data.get("max_marks", 1),
                        "sub_parts": q_data.get("sub_parts", []),
                        "marking_scheme": q_data.get("marking_scheme", []),
                        "reference_resource_id": mapped_id,
                        "reference_resource_title": r_title_clean if r_title_clean else None,
                        "reference_quote": q_data.get("reference_quote"),
                    }
                )

        if not normalized_questions:
            raise ValueError("No valid questions could be extracted.")

        questions_data = normalized_questions

        progress_callback(80, "Mapping references via embeddings fallback...")

        subject_resource_ids = [rid for rid, _ in resource_titles]

        order = 0
        for q_data in questions_data:
            if subject_resource_ids:
                try:
                    chunks = retrieve_relevant_chunks(
                        q_data.get("question_text", ""), subject_resource_ids, db, top_k=1
                    )
                    if chunks:
                        if not q_data.get("reference_resource_id"):
                            q_data["reference_resource_id"] = chunks[0]["resource_id"]
                        if not q_data.get("reference_resource_title"):
                            for rid, rtitle in resource_titles:
                                if rid == chunks[0]["resource_id"]:
                                    q_data["reference_resource_title"] = rtitle
                                    break
                        if not q_data.get("reference_quote"):
                            q_data["reference_quote"] = chunks[0].get("text", "")[:200]
                        q_data["reference_chunk_position"] = chunks[0].get("position")
                except Exception:
                    pass
            q_data["order"] = order
            q_data["original_number"] = str(q_data.get("original_number", ""))
            q_data["id"] = str(order + 1)
            order += 1

        StorageManager.save_exercise_json(exercise.id, questions_data)
        exercise.content_path = StorageManager._get_exercise_path(exercise.id)

        exercise.processing_time_ms = int((time.time() - start_time) * 1000)
        exercise.updated_at = datetime.utcnow()
        db.commit()

        progress_callback(100, "Processing complete")
        if task_id:
            TaskManager._update_db_task(task_id, status="completed", progress=100)

    except Exception as e:
        logger.error(f"Error processing exercise {exercise_id}: {e}", exc_info=True)
        if task_id:
            TaskManager._update_db_task(task_id, status="failed", error=str(e))
        raise
    finally:
        db.close()


def _fallback_grade(
    question: dict, user_answer: str, max_marks: int, answer_text: str, error: str = ""
) -> "GradeResponse":
    """Basic keyword-match fallback when AI grading is unavailable."""
    from app.schemas.exercise import CriterionResult, GradeResponse

    ua_lower = (user_answer or "").strip().lower()
    ca_lower = (answer_text or "").strip().lower()

    if not ua_lower:
        return GradeResponse(
            total_awarded=0, total_max=max_marks,
            criterion_results=[
                CriterionResult(criterion="Overall correctness", max_points=max_marks, awarded_points=0, rationale="No answer provided.")
            ],
            feedback="No answer provided.", correct_answer=answer_text,
        )

    key_words = [w for w in ca_lower.split() if len(w) > 3]
    if not key_words:
        key_words = ca_lower.split()
    matched = sum(1 for w in key_words if w in ua_lower)
    ratio = matched / max(len(key_words), 1)
    awarded = round(max_marks * ratio)
    if awarded == 0 and ua_lower and len(ua_lower) > 5:
        awarded = round(max_marks * 0.25)

    return GradeResponse(
        total_awarded=min(awarded, max_marks),
        total_max=max_marks,
        criterion_results=[
            CriterionResult(
                criterion="Overall correctness",
                max_points=max_marks,
                awarded_points=min(awarded, max_marks),
                rationale=f"Matched {matched}/{len(key_words)} key terms from the correct answer."
                         if matched > 0 else "No key terms matched. AI unavailable for detailed grading.",
            )
        ],
        feedback=f"Basic match: {matched}/{len(key_words)} key terms. AI grading unavailable.",
        correct_answer=answer_text,
    )


def grade_answer(
    user: User, question: dict[str, Any], user_answer: str
) -> "GradeResponse":
    """Grades a user's answer using the LLM for subjective questions,
    returning per-criterion mark breakdown."""
    from app.schemas.exercise import CriterionResult, GradeResponse

    client = AIClient(category="chat")

    question_text = question.get("question_text", "")
    answer_text = question.get("answer_text", "")
    max_marks = question.get("max_marks", 1) or 1
    marking_scheme = question.get("marking_scheme", [])
    sub_parts = question.get("sub_parts", [])

    # Objective questions: full marks or zero with single criterion
    if question.get("question_type") == "objective":
        is_correct = user_answer.strip().lower() == answer_text.strip().lower()
        return GradeResponse(
            total_awarded=max_marks if is_correct else 0,
            total_max=max_marks,
            criterion_results=[
                CriterionResult(
                    criterion="Correct answer",
                    max_points=max_marks,
                    awarded_points=max_marks if is_correct else 0,
                    rationale="Answer matches the correct answer exactly."
                    if is_correct
                    else "Answer does not match the correct answer.",
                )
            ],
            feedback="Correct!" if is_correct else "Incorrect.",
            correct_answer=answer_text,
        )

    prompt = f"""
Question: {question_text}
Correct Answer: {answer_text}
Max Marks: {max_marks}
Marking Scheme: {json.dumps(marking_scheme if marking_scheme else [])}
Sub-parts: {json.dumps(sub_parts if sub_parts else [])}
User's Answer: {user_answer}

Evaluate the user's answer against EACH criterion in the marking scheme.
For each criterion, determine the points awarded and explain why.
Return a strict JSON object with these keys:
- "total_awarded": integer, total marks awarded across all criteria
- "total_max": integer, should equal {max_marks}
- "criterion_results": array of objects, each with:
    - "criterion": the criterion name
    - "max_points": max points for this criterion
    - "awarded_points": points awarded (0 to max_points)
    - "rationale": brief explanation of why these points were awarded or deducted
- "feedback": brief 1-2 sentence summary of the overall evaluation

If there is NO marking scheme, evaluate holistically and return a single criterion "Overall correctness".
Do NOT include markdown formatting. Return only the raw JSON.
"""
    system_prompt = (
        "You are a teacher grading a student's answer. "
        "Use the marking scheme to award partial credit fairly. "
        "Be lenient with typos and alternative phrasings as long as the concept is correct. "
        "Address the student as 'you' in feedback and rationale (e.g. 'You correctly explained...' not 'The student explained...'). "
        "Award full marks for a criterion if you demonstrate understanding of that point."
    )

    try:
        response = _run_async(
            client.generate_text, prompt=prompt, system_instruction=system_prompt,
            max_tokens=4000, raw_output=True, require_reasoning=True
        )
        if not response or not response.strip():
            raise ValueError("Empty response from AI")
        json_text = response.strip()
        if json_text.startswith("```json"):
            json_text = json_text[7:]
        if json_text.startswith("```"):
            json_text = json_text[3:]
        if json_text.endswith("```"):
            json_text = json_text[:-3]
        result = json.loads(json_text.strip())
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            raise ValueError(f"Expected JSON object, got {type(result).__name__}")
        criterion_results = []
        for cr in result.get("criterion_results", []):
            if isinstance(cr, dict):
                criterion_results.append(
                    CriterionResult(
                        criterion=str(cr.get("criterion", "Criterion")),
                        max_points=int(cr.get("max_points", max_marks)),
                        awarded_points=int(cr.get("awarded_points", 0)),
                        rationale=str(cr.get("rationale", "")),
                    )
                )
        if not criterion_results:
            total_awarded = result.get("total_awarded", 0)
            criterion_results = [
                CriterionResult(
                    criterion="Overall correctness",
                    max_points=max_marks,
                    awarded_points=int(total_awarded),
                    rationale=result.get("feedback", ""),
                )
            ]
        return GradeResponse(
            total_awarded=result.get("total_awarded", 0),
            total_max=result.get("total_max", max_marks),
            criterion_results=criterion_results,
            feedback=result.get("feedback", ""),
            correct_answer=answer_text,
        )
    except Exception as e:
        logger.warning(f"AI grading failed: {e}. Falling back to keyword match.")
        return _fallback_grade(question, user_answer, max_marks, answer_text, str(e))


def explain_answer(
    user: User, question: dict[str, Any], user_answer: str | None = None,
    view_mode: str = "hide", ai_mode: str = "elaborate",
    output_format: str = "markdown", scope: str = "source"
) -> str:
    """Generates an explanation for the correct answer

    Args:
        user: The user requesting the explanation
        question: The question dict containing question_text and answer_text
        user_answer: Optional user's attempt at the question
        view_mode: The current viewing mode ('hide', 'show', 'interactive', 'exam', 'conversation')
        ai_mode: AI mode (quick, simple, normal, elaborate, eli5)
        output_format: Output format preference
        scope: Context scope (source, web, both)
    """
    client = AIClient(category="chat")

    question_text = question.get("question_text", "")
    answer_text = question.get("answer_text", "")

    prompt = f"""
Question: {question_text}
Correct Answer: {answer_text}
"""
    # Only include user attempt if they provided one AND we're in an interactive/exam mode
    has_user_answer = user_answer and user_answer.strip()
    is_interactive_mode = view_mode in ("interactive", "exam", "conversation")

    if has_user_answer and is_interactive_mode:
        prompt += f"\nUser's Attempt: {user_answer}"

    # Determine length/style based on ai_mode
    length_instructions = {
        "quick": "Keep it VERY brief — 1-2 short sentences. No formatting.",
        "simple": "Keep it concise — 2-3 sentences. Simple language, no fluff.",
        "normal": "Write a brief paragraph covering the key point. Use plain markdown.",
        "elaborate": "Explain thoroughly with detail. Use markdown formatting freely.",
        "eli5": "Explain like I'm 5 — short analogy or simple terms, 2-3 sentences.",
    }
    length_instr = length_instructions.get(ai_mode, length_instructions["quick"])

    if is_interactive_mode and has_user_answer:
        system_prompt = (
            f"{length_instr} "
            "Evaluate the user's attempt and state if it is correct or wrong, "
            "then briefly explain the key concept."
        )
    else:
        system_prompt = (
            f"{length_instr} "
            "Briefly explain the correct answer and the key concept."
        )

    result = _run_async(
        client.generate_text, prompt=prompt, system_instruction=system_prompt,
        max_tokens=4000, raw_output=True, require_reasoning=True
    )
    return (result or "").strip()


def generate_exercise_task(
    exercise_id: str, user_id: int, req_data: dict[str, Any], task_id: str | None = None, **kwargs
):
    db = SessionLocal()
    try:
        exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
        user = db.query(User).filter(User.id == user_id).first()
        if not exercise or not user:
            if task_id:
                TaskManager._update_db_task(
                    task_id, status="failed", error="Exercise or User not found"
                )
            return

        def progress_callback(percent, message=None):
            if task_id:
                TaskManager.update_task_progress(task_id, percent, message=message)

        progress_callback(10, "Fetching resources...")
        start_time = time.time()

        resource_ids = req_data.get("resource_ids", [])
        exercise_ids = req_data.get("exercise_ids", [])
        resources_text = ""
        title_to_id = {}
        for r_id in resource_ids:
            r = db.query(Resource).filter(Resource.id == r_id, Resource.user_id == user_id).first()
            if r:
                r_text = StorageManager.get_resource_text(r.id)
                if r_text:
                    title_to_id[r.title.strip()] = r.id
                    resources_text += f"\n--- {r.title} ---\n{r_text}\n"

        for ex_id in exercise_ids:
            ex = (
                db.query(Exercise).filter(Exercise.id == ex_id, Exercise.user_id == user_id).first()
            )
            if ex:
                questions = StorageManager.get_exercise_json(ex.id)
                if questions:
                    ex_text = ""
                    for q in questions:
                        q_text = q.get("question_text", "")
                        a_text = q.get("answer_text", "")
                        ex_text += f"Q: {q_text}\nA: {a_text}\n\n"
                    resources_text += f"\n--- Existing Exercise: {ex.title} ---\n{ex_text}\n"

        has_exercise_content = len(exercise_ids) > 0

        if not resources_text.strip():
            raise ValueError("No content found in the selected resources.")

        if len(resources_text) > 30000:
            resources_text = resources_text[:30000] + "... [truncated]"

        progress_callback(40, "Using AI to generate exercise...")

        question_types = req_data.get("question_types", [])
        lengths = req_data.get("lengths", [])
        difficulties = req_data.get("difficulties", [])
        num_questions = req_data.get("num_questions", 5)

        types_str = ", ".join(question_types)
        lengths_str = ", ".join(lengths)
        diff_str = ", ".join(difficulties)

        advanced = req_data.get("advanced", False)
        distribution = req_data.get("distribution", {})

        all_questions_data = []
        BATCH_SIZE = 20
        remaining_questions = num_questions

        rem_dist = dict(distribution) if advanced else {}
        chunk_index = 0

        while remaining_questions > 0:
            chunk_size = min(BATCH_SIZE, remaining_questions)

            if advanced and rem_dist:

                def get_chunk_dist(keys, size, total):
                    c_dist = {}
                    allocated = 0
                    for k in keys:
                        amount = min(
                            rem_dist.get(k, 0), round((rem_dist.get(k, 0) / max(1, total)) * size)
                        )
                        c_dist[k] = amount
                        allocated += amount

                    diff = size - allocated
                    sorted_keys = sorted(keys, key=lambda x: rem_dist.get(x, 0), reverse=True)
                    while diff != 0:
                        for k in sorted_keys:
                            if diff > 0 and rem_dist.get(k, 0) > c_dist[k]:
                                c_dist[k] += 1
                                diff -= 1
                                break
                            elif diff < 0 and c_dist[k] > 0:
                                c_dist[k] -= 1
                                diff += 1
                                break
                        else:
                            break
                    return c_dist

                c_diff = get_chunk_dist(["easy", "medium", "hard"], chunk_size, remaining_questions)
                c_len = get_chunk_dist(["short", "medLen", "long"], chunk_size, remaining_questions)
                c_type = get_chunk_dist(
                    ["typeShort", "typeLong", "typeObj", "typeFill"],
                    chunk_size,
                    remaining_questions,
                )

                dist_diff = f"{c_diff.get('easy', 0)} Easy, {c_diff.get('medium', 0)} Medium, {c_diff.get('hard', 0)} Hard"
                dist_len = f"{c_len.get('short', 0)} Short, {c_len.get('medLen', 0)} Medium, {c_len.get('long', 0)} Long"
                dist_type = f"{c_type.get('typeShort', 0)} Short Answer, {c_type.get('typeLong', 0)} Long Answer, {c_type.get('typeObj', 0)} Objective (Multiple Choice), {c_type.get('typeFill', 0)} Fill in the blank"

                prompt = f"""Generate exactly {chunk_size} quiz questions based on the following content.

Target question types distribution: {dist_type}.
Target question lengths distribution: {dist_len}.
Target question difficulties distribution: {dist_diff}.
"""
            else:
                prompt = f"""Generate exactly {chunk_size} quiz questions based on the following content.

The questions MUST be of the following types: {types_str}.
Target lengths: {lengths_str}.
Target difficulties: {diff_str}.
If "mixed" is specified, provide a relatively even mix of 'objective' (multiple choice), 'subjective' (short answer), and 'fill_in_the_blank'.
"""
            if has_exercise_content:
                prompt += """
IMPORTANT: The content above includes existing exercise questions and answers. You MUST generate DIFFERENT questions on the same topics — do NOT simply rephrase the existing questions. Create new questions that test understanding of the same core concepts but from different angles, using different wording, different examples, and different specific details. The result should be a fresh set of questions that cover similar material but are clearly distinct from the provided ones.
"""

            if all_questions_data:
                previous_questions = "\n".join(
                    [
                        f"- {q.get('question_text', '').replace('```', '')}"
                        for q in all_questions_data[-50:]
                    ]
                )
                prompt += f"""
IMPORTANT: You have already generated the following questions in previous batches. DO NOT generate duplicate questions or questions covering the exact same specific concept:
{previous_questions}
"""

            prompt += f"""
Content:
{resources_text}

Format the response as a strict JSON array of objects. Do not wrap it in markdown codeblocks like ```json, just output the raw JSON array.
Each object must have the following keys:
- "question_text": The actual question. For fill in the blank, use "_____" to represent the blank.
- "answer_text": The correct answer (for AI and user reference).
- "question_type": Must be exactly one of: "objective", "subjective", "fill_in_the_blank".
- "options": (ONLY for "objective" type) a list of 4 string options containing the correct answer and 3 distractors. Leave as null for other types.
- "topic": A short 1-4 word description of the specific topic or concept this question covers.
- "difficulty": Must be "Easy", "Medium", or "Hard".
- "max_marks": Total marks available for this question (integer). Assign marks proportionally based on complexity.
- "sub_parts": Array of sub-questions if the question has distinct parts (a, b, c or i, ii, iii). Each with:
    - "label": The part label (e.g., "a", "b").
    - "question_text": The sub-part question text.
    - "answer_text": The sub-part answer.
    - "max_marks": Marks for this sub-part.
    - "sub_parts": Nested sub-parts for further decomposition (max 3 levels).
    - "question_type": Classification for this sub-part.
    - "options": For objective sub-parts.
- "marking_scheme": **REQUIRED for subjective and fill_in_the_blank questions.** Array of 1–4 marking criteria. MUST NOT be empty for these types. Each criterion:
    - "criterion": Short name (e.g., "Correct formula", "Key term used", "Explanation quality").
    - "max_points": Points for this criterion. All criterion max_points MUST sum to the question's max_marks.
    - "description": What the student must demonstrate to earn these points.
  For objective questions, set "marking_scheme" to [].
- "resource_title": The exact title of the resource (from the --- Title --- headers above) that this question was derived from.
- "reference_quote": A short, exact excerpt or line from the content that supports the answer.

Respond with ONLY the JSON array.
"""

            client = AIClient(category="processing")
            response = _run_async(
                client.generate_text,
                prompt=prompt,
                system_instruction="You are an expert educational content generator.",
                max_tokens=8192,
                raw_output=True,
                require_reasoning=False,
            )

            try:
                json_text = response.strip()
                if json_text.startswith("```json"):
                    json_text = json_text[7:]
                if json_text.startswith("```"):
                    json_text = json_text[3:]
                if json_text.endswith("```"):
                    json_text = json_text[:-3]
                questions_data = json.loads(json_text.strip())
                if isinstance(questions_data, list):
                    valid_questions = []
                    for q in questions_data:
                        if isinstance(q, dict) and "question_text" in q:
                            q = _normalize_question_structure(q)
                            valid_questions.append(q)
                    all_questions_data.extend(valid_questions)
                else:
                    valid_questions = []

                if advanced and rem_dist:
                    for k, v in c_diff.items():
                        rem_dist[k] = max(0, rem_dist[k] - v)
                    for k, v in c_len.items():
                        rem_dist[k] = max(0, rem_dist[k] - v)
                    for k, v in c_type.items():
                        rem_dist[k] = max(0, rem_dist[k] - v)

            except json.JSONDecodeError:
                pass

            remaining_questions -= chunk_size
            chunk_index += 1
            progress_callback(
                40 + int((chunk_index * BATCH_SIZE / num_questions) * 40),
                f"Generated {len(all_questions_data)}/{num_questions} questions...",
            )

            if remaining_questions > 0:
                time.sleep(3)

        progress_callback(80, "Mapping references to your resources...")

        lookup_resource_ids = resource_ids[:]
        resource_id_to_title = {v: k for k, v in title_to_id.items()}

        if not lookup_resource_ids:
            subject_resources = (
                db.query(Resource.id, Resource.title)
                .filter(Resource.subject_id == exercise.subject_id, Resource.user_id == user_id)
                .all()
            )
            lookup_resource_ids = [r.id for r in subject_resources]
            for r_id, r_title in subject_resources:
                resource_id_to_title[r_id] = r_title

        order = 0
        for q in all_questions_data:
            q["original_number"] = str(q.get("original_number", order + 1))
            q["order"] = order
            q["id"] = str(order + 1)

            try:
                chunks = retrieve_relevant_chunks(
                    q.get("question_text", ""), lookup_resource_ids, db, top_k=1
                )
                if chunks:
                    q["reference_resource_id"] = chunks[0]["resource_id"]
                    q["reference_resource_title"] = resource_id_to_title.get(
                        chunks[0]["resource_id"]
                    )
                    q["reference_quote"] = chunks[0].get("text", "")[:300]
                    q["reference_chunk_position"] = chunks[0].get("position")
            except Exception as e:
                logger.warning(f"Embedding lookup failed for question {order}: {e}")

            order += 1

        StorageManager.save_exercise_json(exercise_id, all_questions_data)
        exercise.content_path = StorageManager._get_exercise_path(exercise_id)

        exercise.processing_time_ms = int((time.time() - start_time) * 1000)
        exercise.updated_at = datetime.utcnow()
        db.commit()

        progress_callback(100, "Exercise generation complete.")
        if task_id:
            TaskManager._update_db_task(task_id, status="completed", progress=100)

    except Exception as e:
        logger.error(f"Exercise generation failed: {e!s}")
        if task_id:
            TaskManager._update_db_task(task_id, status="failed", error=str(e))
        raise
    finally:
        db.close()
