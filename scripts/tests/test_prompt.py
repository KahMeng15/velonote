import json
from app.processing.ai_client import AIClient
from app.processing.exercise_processor import _try_parse_import_payload
import asyncio

text = """
# QUESTION 1
Two relations R1 and R2 are defined as below:
R1 = {(2,2), (3,1), (3,5)}
R2 = {(1,2), (2,1), (3,1)}
Combine the relations using the following set operations.
![image_1](test.png)
## Jawapan / Answer
{(1,2), (2,1), (2,2), (3,1), (3,5)} [1M] i.
"""

prompt = f"""Extract and structure all quiz questions from the following text.
Text to process:
---
{text}
---

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

async def run():
    client = AIClient()
    res = await client.generate_text(
        prompt=prompt,
        system_instruction="You are an expert educational content extractor.",
        max_tokens=2048,
        require_reasoning=True
    )
    data = _try_parse_import_payload(res)
    print("SUCCESS: JSON Parsed.")
    print("QUESTION 1 text:", repr(data["questions"][0]["question_text"]))

asyncio.run(run())
