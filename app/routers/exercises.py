"""Exercises management endpoints"""

import logging
import os
import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db import Exercise, Subject, User
from app.processing.document_generator import ContentSegment, ContentType
from app.processing.exercise_processor import (
    explain_answer,
    grade_answer,
)
from app.schemas.exercise import (
    ExerciseCheckRequest,
    ExerciseExplainRequest,
    ExerciseGenerateRequest,
    ExerciseResponse,
    ExerciseSessionSubmit,
    ExerciseStateSave,
    GradeResponse,
)
from app.utils.auth import get_current_user
from app.utils.db import generate_random_id, get_db
from app.utils.storage import StorageManager
from app.utils.tasks import TaskManager

_export_progress = {}

logger = logging.getLogger(__name__)


def _find_question_recursive(questions: list[dict], question_id: str) -> dict | None:
    """Find a question or sub-part by ID recursively."""
    for q in questions:
        if str(q.get("id")) == str(question_id):
            return q
        for sp in q.get("sub_parts", []):
            found = _find_sub_part_recursive(sp, question_id)
            if found:
                return found
    return None


def _find_sub_part_recursive(part: dict, target_id: str) -> dict | None:
    """Recursively search sub-parts by ID."""
    if str(part.get("id")) == str(target_id):
        return part
    for sp in part.get("sub_parts", []):
        found = _find_sub_part_recursive(sp, target_id)
        if found:
            return found
    return None


router = APIRouter(
    prefix="/exercises", tags=["exercises"], responses={401: {"description": "Unauthorized"}}
)


@router.get("", response_model=list[ExerciseResponse])
def get_all_exercises(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get all exercises for the current user"""
    exercises = (
        db.query(Exercise)
        .filter(Exercise.user_id == current_user.id)
        .order_by(Exercise.updated_at.desc())
        .all()
    )

    response_exercises = []
    for ex in exercises:
        ex_data = ExerciseResponse.from_orm(ex)
        params = StorageManager.get_resource_json(ex.id, "parameters")
        if params:
            ex_data.parameters = params
        questions = StorageManager.get_exercise_json(ex.id)
        if questions:
            ex_data.questions = _ensure_question_defaults(questions)
        response_exercises.append(ex_data)
    return response_exercises


@router.get("/subject/{subject_id}", response_model=list[ExerciseResponse])
def get_exercises_by_subject(
    subject_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get all exercises for a subject"""
    exercises = (
        db.query(Exercise)
        .filter(Exercise.subject_id == subject_id, Exercise.user_id == current_user.id)
        .order_by(Exercise.created_at.desc())
        .all()
    )

    response_exercises = []
    for ex in exercises:
        ex_data = ExerciseResponse.from_orm(ex)
        params = StorageManager.get_resource_json(ex.id, "parameters")
        if params:
            ex_data.parameters = params
        questions = StorageManager.get_exercise_json(ex.id)
        if questions:
            ex_data.questions = _ensure_question_defaults(questions)
        response_exercises.append(ex_data)
    return response_exercises


@router.get("/{exercise_id}", response_model=ExerciseResponse)
def get_exercise(
    exercise_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get specific exercise"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    ex_data = ExerciseResponse.from_orm(exercise)
    params = StorageManager.get_resource_json(exercise.id, "parameters")
    if params:
        ex_data.parameters = params
    questions = StorageManager.get_exercise_json(exercise.id)
    if questions:
        ex_data.questions = _ensure_question_defaults(questions)
    return ex_data


def _ensure_question_defaults(questions: list[dict]) -> list[dict]:
    """Backward-compat: fill in default marks, sub_parts, marking_scheme for old questions."""
    for q in questions:
        q.setdefault("max_marks", 1)
        q.setdefault("sub_parts", [])
        q.setdefault("marking_scheme", [])
        for sp in q.get("sub_parts", []):
            sp.setdefault("max_marks", 1)
            sp.setdefault("sub_parts", [])
            sp.setdefault("marking_scheme", [])
            for ssp in sp.get("sub_parts", []):
                ssp.setdefault("max_marks", 1)
                ssp.setdefault("sub_parts", [])
                ssp.setdefault("marking_scheme", [])
    return questions


@router.put("/{exercise_id}/content", response_model=ExerciseResponse)
def update_exercise_content(
    exercise_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update exercise questions (JSON)"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    questions = payload.get("questions", [])
    from app.processing.exercise_processor import _normalize_question_structure
    questions = [_normalize_question_structure(q) for q in questions]
    StorageManager.save_exercise_json(exercise.id, questions)

    exercise.updated_at = datetime.utcnow()
    db.commit()

    ex_data = ExerciseResponse.from_orm(exercise)
    ex_data.questions = questions
    return ex_data


@router.post("/upload", response_model=ExerciseResponse)
def upload_exercise(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a file to process into an exercise"""
    subject = (
        db.query(Subject)
        .filter(Subject.id == subject_id, Subject.user_id == current_user.id)
        .first()
    )
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Save file
    file_id = generate_random_id(db, Exercise)
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    file_path = StorageManager.get_upload_path(current_user.id, f"{file_id}{ext}")

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    exercise = Exercise(
        id=file_id,
        user_id=current_user.id,
        subject_id=subject_id,
        group_id=subject.group_id,
        title=os.path.splitext(file.filename)[0] if file.filename else "Uploaded Exercise",
        file_path=file_path,
        file_name=file.filename,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)

    # Launch background task to process the file and extract questions
    task_id = f"extract_{file_id}"
    TaskManager.submit_task(
        task_id=task_id,
        user_id=current_user.id,
        task_type="exercise_extraction",
        exercise_id=file_id,
        title=exercise.title,
    )

    return exercise


@router.post("/merge", response_model=ExerciseResponse)
def merge_exercises(
    exercise_ids: list[str],
    title: str = "Merged Exercise",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Merge multiple exercises into a new one"""
    if not exercise_ids:
        raise HTTPException(status_code=400, detail="No exercises provided")

    exercises = (
        db.query(Exercise)
        .filter(Exercise.id.in_(exercise_ids), Exercise.user_id == current_user.id)
        .all()
    )

    if not exercises:
        raise HTTPException(status_code=404, detail="Exercises not found")

    subject_id = exercises[0].subject_id

    new_ex_id = generate_random_id(db, Exercise)
    new_ex = Exercise(
        id=new_ex_id,
        user_id=current_user.id,
        subject_id=subject_id,
        title=title,
        group_id=exercises[0].group_id,
    )
    db.add(new_ex)

    order = 0
    for ex in exercises:
        for q in ex.questions:
            new_q = ExerciseQuestion(
                exercise_id=new_ex_id,
                question_text=q.question_text,
                answer_text=q.answer_text,
                question_type=q.question_type,
                options=q.options,
                original_number=q.original_number,
                order=order,
                explanation=q.explanation,
                reference_note_id=q.reference_note_id,
            )
            db.add(new_q)
            order += 1

    db.commit()
    db.refresh(new_ex)
    return new_ex


@router.post("/{exercise_id}/questions/{question_id}/grade", response_model=GradeResponse)
def grade_exercise_answer(
    exercise_id: str,
    question_id: str,
    req: ExerciseCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grade an answer with per-criterion mark breakdown"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    questions = StorageManager.get_exercise_json(exercise_id) or []
    question = _find_question_recursive(questions, question_id)

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    from app.processing.exercise_processor import _normalize_question_structure

    question = _normalize_question_structure(question)
    return grade_answer(current_user, question, req.user_answer)


@router.post("/{exercise_id}/submit")
def submit_exercise_session(
    exercise_id: str,
    payload: ExerciseSessionSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save graded exercise session to study_sessions with mark breakdown"""
    from app.models.db import StudySession

    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    session = StudySession(
        user_id=current_user.id,
        exercise_id=exercise_id,
        resource_id=exercise.resource_id,
        session_type="exercise",
        total_marks=payload.total_marks,
        awarded_marks=payload.awarded_marks,
        question_scores=payload.question_scores,
        duration_minutes=payload.duration_minutes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "message": "Session saved",
        "session_id": session.id,
        "awarded_marks": payload.awarded_marks,
        "total_marks": payload.total_marks,
    }


@router.post("/{exercise_id}/questions/{question_id}/explain")
def explain_exercise_answer(
    exercise_id: str,
    question_id: str,
    req: ExerciseExplainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an AI explanation for the question"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    questions = StorageManager.get_exercise_json(exercise_id) or []
    question = _find_question_recursive(questions, question_id)

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    explanation = explain_answer(
        current_user, question,
        user_answer=req.user_answer,
        view_mode=req.view_mode or "hide",
        ai_mode=req.ai_mode,
        output_format=req.output_format,
        scope=req.scope,
    )

    # Save the generated explanation back to JSON so it persists
    question["explanation"] = explanation
    StorageManager.save_exercise_json(exercise_id, questions)

    return {"explanation": explanation}


@router.get("/{exercise_id}/sessions")
def get_exercise_sessions(
    exercise_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return past study sessions for this exercise"""
    from app.models.db import StudySession

    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    sessions = (
        db.query(StudySession)
        .filter(
            StudySession.exercise_id == exercise_id,
            StudySession.user_id == current_user.id,
        )
        .order_by(StudySession.created_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "session_type": s.session_type,
            "duration_minutes": s.duration_minutes,
            "total_marks": s.total_marks,
            "awarded_marks": s.awarded_marks,
            "question_scores": s.question_scores,
            "questions_attempted": s.questions_attempted,
            "questions_correct": s.questions_correct,
            "score": s.score,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ]


@router.delete("/{exercise_id}/questions/{question_id}/explain")
def delete_exercise_explanation(
    exercise_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an AI explanation for the question"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    questions = StorageManager.get_exercise_json(exercise_id) or []
    question = _find_question_recursive(questions, question_id)

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    question["explanation"] = None
    StorageManager.save_exercise_json(exercise_id, questions)

    return {"message": "Explanation deleted"}


@router.delete("/{exercise_id}")
def delete_exercise(
    exercise_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Delete an exercise"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    # Clean up physical files
    if exercise.file_path and os.path.exists(exercise.file_path):
        try:
            os.remove(exercise.file_path)
        except Exception:
            pass

    StorageManager.delete_exercise_files(exercise_id)

    db.delete(exercise)
    db.commit()
    return {"status": "success"}


@router.post("/generate", response_model=ExerciseResponse)
def generate_exercise(
    req: ExerciseGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an exercise using AI from resources"""
    subject = (
        db.query(Subject)
        .filter(Subject.id == req.subject_id, Subject.user_id == current_user.id)
        .first()
    )
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    file_id = generate_random_id(db, Exercise)

    title = req.title.strip() if req.title and req.title.strip() else None
    if not title:
        if req.resource_ids:
            from app.models.db import Resource

            resources = db.query(Resource).filter(Resource.id.in_(req.resource_ids)).all()
            titles = [r.title for r in resources if r.title]

            import re

            def format_ranges(nums):
                if not nums:
                    return ""
                sorted_nums = sorted(set(nums))
                ranges = []
                start = end = sorted_nums[0]
                for n in sorted_nums[1:]:
                    if n == end + 1:
                        end = n
                    else:
                        ranges.append(str(start) if start == end else f"{start}-{end}")
                        start = end = n
                ranges.append(str(start) if start == end else f"{start}-{end}")
                if len(ranges) == 1:
                    return ranges[0]
                elif len(ranges) == 2:
                    return f"{ranges[0]} & {ranges[1]}"
                return ", ".join(ranges[:-1]) + f", {ranges[-1]}"

            extracted_nums = []
            common_prefix = None
            valid_extraction = True
            for t in titles:
                m = re.match(r"^([A-Za-z]+)\s*(\d+)", t.strip(), re.IGNORECASE)
                if m:
                    prefix = m.group(1).title()
                    num = int(m.group(2))
                    if common_prefix is None:
                        common_prefix = prefix
                    elif common_prefix != prefix:
                        common_prefix = "Resource"
                    extracted_nums.append(num)
                else:
                    valid_extraction = False
                    break

            if valid_extraction and extracted_nums:
                ranges_str = format_ranges(extracted_nums)
                base_title = f"{common_prefix} {ranges_str} Exercise"
            else:
                if len(titles) > 2:
                    base_title = f"{titles[0]} + {len(titles) - 1} others Exercise"
                elif titles:
                    base_title = f"{' & '.join(titles)} Exercise"
                else:
                    base_title = "Generated Exercise"
        else:
            base_title = "Generated Exercise"

        import re

        existing_exs = (
            db.query(Exercise)
            .filter(
                Exercise.subject_id == req.subject_id,
                Exercise.user_id == current_user.id,
                Exercise.title.like(f"{base_title}%"),
            )
            .all()
        )

        if existing_exs:
            max_counter = 0
            for ex in existing_exs:
                if ex.title == base_title:
                    max_counter = max(max_counter, 1)
                else:
                    m = re.search(r" (\d+)$", ex.title)
                    if m:
                        max_counter = max(max_counter, int(m.group(1)))
            if max_counter > 0:
                title = f"{base_title} {max_counter + 1}"
            else:
                title = base_title
        else:
            title = base_title

    exercise = Exercise(
        id=file_id,
        user_id=current_user.id,
        subject_id=req.subject_id,
        group_id=subject.group_id,
        title=title,
        model=current_user.ai_model or get_settings().GLOBAL_AI_TIER1_MODEL,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)

    db.refresh(exercise)

    StorageManager.save_resource_json(file_id, "parameters", req.dict())

    task_id = f"generate_{file_id}"
    TaskManager.submit_task(
        task_id=task_id,
        user_id=current_user.id,
        task_type="exercise_generation",
        exercise_id=file_id,
        req_data=req.dict(),
        title=title,
    )

    ex_data = ExerciseResponse.from_orm(exercise)
    ex_data.parameters = req.dict()
    return ex_data


@router.patch("/{exercise_id}/rename", response_model=ExerciseResponse)
def rename_exercise(
    exercise_id: str,
    req: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    if "title" in req:
        exercise.title = req["title"]
        db.commit()
        db.refresh(exercise)

    ex_data = ExerciseResponse.from_orm(exercise)
    params = StorageManager.get_resource_json(exercise.id, "parameters")
    if params:
        ex_data.parameters = params
    return ex_data


@router.post("/{exercise_id}/reprocess", response_model=ExerciseResponse)
def reprocess_exercise(
    exercise_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    params = StorageManager.get_resource_json(exercise.id, "parameters")

    # Based on whether it's an uploaded file or generated
    if exercise.file_path and os.path.exists(exercise.file_path):
        task_id = f"extract_{exercise_id}"
        TaskManager.submit_task(
            task_id=task_id,
            user_id=current_user.id,
            task_type="exercise_extraction",
            exercise_id=exercise_id,
            title=exercise.title,
        )
    elif params:
        task_id = f"generate_{exercise_id}"
        TaskManager.submit_task(
            task_id=task_id,
            user_id=current_user.id,
            task_type="exercise_generation",
            exercise_id=exercise_id,
            req_data=params,
            title=exercise.title,
        )
    else:
        raise HTTPException(
            status_code=400, detail="Cannot reprocess: missing file or generation parameters"
        )

    ex_data = ExerciseResponse.from_orm(exercise)
    if params:
        ex_data.parameters = params
    return ex_data


@router.get("/{exercise_id}/processing-logs")
async def get_exercise_processing_logs(
    exercise_id: str,
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )

    if not exercise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")

    import re

    from app.logging_config import LOGS_DIR
    from app.utils.storage import StorageManager

    # Include the per-entity process log first (most relevant)
    per_entity_log = StorageManager.get_process_log(exercise_id)

    log_files = ["processing.log", "worker.log", "backend.log", "errors.log"]
    entries = []

    for log_file in log_files:
        log_path = os.path.join(LOGS_DIR, log_file)
        if not os.path.exists(log_path):
            continue
        try:
            max_bytes = 5 * 1024 * 1024
            with open(log_path, encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)
                file_size = f.tell()
                start = max(0, file_size - max_bytes)
                f.seek(start)
                if start > 0:
                    f.readline()
                lines = f.readlines()

            for line in lines:
                if exercise_id not in line:
                    continue
                if "uvicorn.access" in line:
                    continue
                m = re.match(
                    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)\s+\[(\w+)\]\s+([\w\.]+):\s+(.*)",
                    line.strip(),
                )
                if m:
                    entries.append(
                        {
                            "timestamp": m.group(1),
                            "level": m.group(2),
                            "logger": m.group(3),
                            "message": m.group(4),
                            "source": log_file,
                        }
                    )
                else:
                    entries.append(
                        {
                            "timestamp": "",
                            "level": "INFO",
                            "logger": "unknown",
                            "message": line.strip(),
                            "source": log_file,
                        }
                    )
        except Exception as e:
            logger.error(f"Error reading {log_file}: {e}")

    # sort newest first
    entries.sort(key=lambda x: x["timestamp"], reverse=True)
    if limit > 0:
        entries = entries[:limit]

    return {"entries": entries, "process_log": per_entity_log}


@router.post("/{exercise_id}/export", response_model=dict)
async def export_exercise(
    exercise_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export an exercise to PDF or DOCX using DocumentGenerator"""
    logger.info(f"[Export] Received request for exercise {exercise_id} with body: {body}")
    task_id = str(uuid.uuid4())[:8]
    _export_progress[task_id] = {"step": "Starting", "percent": 0, "status": "running"}

    def progress_callback(step, percent):
        _export_progress[task_id] = {
            "step": step,
            "percent": percent,
            "status": "running" if percent < 100 else "complete",
        }

    export_format = body.get("format", "pdf").lower()
    if export_format not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'docx'")

    include_cover = body.get("include_cover", True)
    template_id = body.get("template_id", None)

    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    questions = (
        db.query(ExerciseQuestion)
        .filter(ExerciseQuestion.exercise_id == exercise.id)
        .order_by(ExerciseQuestion.order)
        .all()
    )
    if not questions:
        raise HTTPException(status_code=400, detail="Exercise has no questions to export.")

    template_config = None
    if template_id:
        from app.models.db import ExportTemplate

        tmpl = (
            db.query(ExportTemplate)
            .filter(
                ExportTemplate.id == template_id,
                (ExportTemplate.user_id == current_user.id) | (ExportTemplate.user_id.is_(None)),
            )
            .first()
        )
        if tmpl:
            template_config = tmpl.config

    segments = []

    if template_config and "header" in template_config:
        h_cfg = template_config["header"]
        if h_cfg.get("show_note_title"):
            segments.append(
                ContentSegment(
                    content=exercise.title, content_type=ContentType.NOTE_TITLE, page_number=1
                )
            )

    import json

    for i, q in enumerate(questions):
        q_text = f"**Q{i + 1}:** {q.question_text}"
        segments.append(ContentSegment(content=q_text, content_type=ContentType.H3, page_number=1))

        if q.question_type == "objective" and q.options:
            try:
                opts = json.loads(q.options) if isinstance(q.options, str) else q.options
                for opt in opts:
                    segments.append(
                        ContentSegment(
                            content=f"- {opt}", content_type=ContentType.LIST, page_number=1
                        )
                    )
            except:
                pass

        ans_text = f"**Answer:** {q.answer_text}"
        segments.append(ContentSegment(content="", content_type=ContentType.BODY, page_number=1))
        segments.append(
            ContentSegment(content=ans_text, content_type=ContentType.BODY, page_number=1)
        )
        segments.append(ContentSegment(content="", content_type=ContentType.BODY, page_number=1))

    try:
        if export_format == "pdf":
            from app.processing.document_generator import DocumentGenerator

            generator = DocumentGenerator(
                resource_id=exercise.id,
                note_title=f"Exercise: {exercise.title}",
            )
            output_path = generator.generate_pdf(
                content_segments=segments,
                extracted_images=[],
                include_toc=False,
                include_cover=include_cover,
                template_config=template_config,
                progress_callback=progress_callback,
            )
        else:
            from app.processing.docx_generator import DocxGenerator

            generator = DocxGenerator(
                resource_id=exercise.id,
                note_title=f"Exercise: {exercise.title}",
            )
            output_path = generator.generate_docx(
                content_segments=segments,
                extracted_images=[],
                include_toc=False,
                include_cover=include_cover,
                template_config=template_config,
                progress_callback=progress_callback,
            )

        _export_progress[task_id] = {
            "step": "Complete",
            "percent": 100,
            "status": "complete",
            "output_path": output_path,
        }

        return {
            "success": True,
            "message": f"{export_format.upper()} generated successfully",
            "download_url": f"/exercises/{exercise.id}/download-export?format={export_format}&task_id={task_id}",
            "task_id": task_id,
            "segments_count": len(segments),
            "images_count": 0,
        }
    except Exception as e:
        logger.error(f"Error exporting {export_format}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{exercise_id}/export-status/{task_id}")
async def get_export_status(
    exercise_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    progress = _export_progress.get(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Task not found")
    return progress


@router.get("/{exercise_id}/download-export")
async def download_export(
    exercise_id: str,
    task_id: str,
    format: str = "pdf",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from fastapi.responses import FileResponse

    export_format = format.lower()
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    progress = _export_progress.get(task_id)
    if not progress or "output_path" not in progress:
        raise HTTPException(status_code=404, detail="Export not ready or task not found")

    output_path = progress["output_path"]
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail=f"{export_format.upper()} file not found.")

    safe_title = "".join(c for c in exercise.title if c.isalnum() or c in (" ", "-", "_")).strip()

    mime_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    return FileResponse(
        path=output_path,
        filename=f"{safe_title}.{export_format}",
        media_type=mime_types.get(export_format, "application/octet-stream"),
    )


@router.get("/{exercise_id}/state")
def get_exercise_state(
    exercise_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load saved exercise state (answers, grades, explanations)"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    state = StorageManager.get_exercise_json(exercise_id, suffix="state")
    if state is None:
        state = {}
    return state


@router.put("/{exercise_id}/state")
def save_exercise_state(
    exercise_id: str,
    req: ExerciseStateSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save exercise state (answers, grades, explanations)"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    StorageManager.save_exercise_json(
        exercise_id, req.model_dump(), suffix="state"
    )
    return {"status": "ok"}


@router.delete("/{exercise_id}/state")
def delete_exercise_state(
    exercise_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete saved exercise state"""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    path = StorageManager._get_exercise_path(exercise_id, suffix="state")
    if os.path.exists(path):
        os.remove(path)
    return {"status": "ok"}


@router.post("/{exercise_id}/upload-image")
async def upload_exercise_image(
    exercise_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")

    import filetype
    kind = filetype.guess(contents)
    if not kind or not kind.mime.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid image file")

    if kind.mime in ["image/gif", "image/svg+xml"]:
        raise HTTPException(status_code=400, detail="GIF and SVG formats are not allowed")

    upload_dir = StorageManager.get_user_images_dir(current_user.id, exercise_id)
    ext = kind.extension

    import io

    from PIL import Image

    try:
        img = Image.open(io.BytesIO(contents))
        if img.mode == 'P':
            img = img.convert('RGBA')
        elif img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGBA')
        max_size = (1920, 1080)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        filename = f"img_{uuid.uuid4().hex}.webp"
        filepath = os.path.join(upload_dir, filename)
        img.save(filepath, 'WEBP', quality=80, method=6)
    except Exception as e:
        logger.error(f"Image compression failed: {e}")
        filename = f"img_{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as f:
            f.write(contents)

    return {"url": f"/api/exercises/{exercise_id}/user-images/{filename}"}


@router.get("/{exercise_id}/user-images/{image_path:path}")
def serve_exercise_user_image(
    exercise_id: str,
    image_path: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from fastapi.responses import FileResponse

    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    if exercise.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    safe_path = os.path.basename(image_path)
    full_path = os.path.join(
        StorageManager.get_user_images_dir(current_user.id, exercise_id), safe_path
    )
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(full_path)
