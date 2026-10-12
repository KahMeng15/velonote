"""Document generation endpoints"""

import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.db import Exercise, Note, Resource, User
from app.processing.ai_client import AIClient
from app.utils.auth import get_current_user
from app.utils.cache import clear_cache_pattern_sync
from app.utils.db import generate_random_id, get_db
from app.utils.quotas import enforce_quota_notes
from app.utils.storage import StorageManager
from app.utils.tasks import TaskManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notes", tags=["notes"])


def format_timestamp(dt: datetime | None) -> str:
    """Format datetime as ISO string with UTC timezone for client-side parsing"""
    if not dt:
        return ""
    # Add UTC timezone info to ensure JS interprets as UTC
    if dt.tzinfo is None:
        # Naive datetime - it's in UTC from our backend
        iso_str = dt.isoformat()
        return iso_str + "Z" if not iso_str.endswith("Z") else iso_str
    else:
        return dt.isoformat()


class NoteRequest(BaseModel):
    resource_id: str | None = None
    resource_ids: list[str] | None = None
    exercise_ids: list[str] | None = None
    mode: str = "elaborate"  # quick, simple, elaborate, eli5
    output_format: str = "sentence"  # sentence, pointform, numbered_list, table
    processing_method: str = "whole"  # whole, section
    split_level: str = "h1"  # h1, h2, h3
    force_regenerate: bool = False
    include_quickread: bool = False  # Generate quick mode summary alongside main summary
    custom_prompt: str | None = None
    title: str | None = None
    prompt_name: str | None = None
    prompt_icon: str | None = None


class NoteResponse(BaseModel):
    resource_id: str
    title: str
    content: str
    is_cached: bool
    summary_type: str = "summary"
    quickread: str | None = None  # Optional quickread summary
    mode: str = "elaborate"
    output_format: str = "sentence"
    processing_method: str = "whole"
    split_level: str | None = None
    processing_time: float | None = None
    processing_time_ms: int | None = None
    model: str | None = None
    is_user_edited: bool = False
    id: str | None = None
    version: int | None = None
    custom_prompt: str | None = None
    prompt_name: str | None = None
    prompt_icon: str | None = None
    exercise_ids: list[str] | None = None


class CheatsheetRequest(BaseModel):
    resource_id: str
    format: str = "markdown"  # markdown or html


class RenameNoteRequest(BaseModel):
    title: str


class CheatsheetResponse(BaseModel):
    resource_id: str
    title: str
    content: str


class NoteItemResponse(BaseModel):
    id: str
    version: int
    resource_id: str | None = None
    note_id: str | None = None
    title: str
    summary_type: str
    file_path: str
    created_at: str
    content: str | None = None
    quickread: str | None = None  # For summaries
    mode: str | None = None  # For summaries (elaborate, quick, simple, eli5)
    output_format: str | None = None  # For summaries (sentence, pointform, numbered_list, table)
    processing_method: str | None = None  # For summaries (whole, section)
    split_level: str | None = None  # For summaries (h1, h2, h3)
    processing_time: float | None = None  # Processing time in seconds
    processing_time_ms: int | None = None  # Processing time in milliseconds
    model: str | None = None  # AI model used
    is_user_edited: bool = False  # Whether the user has edited this summary
    is_pinned: bool = False  # Whether the summary is pinned
    prompt_name: str | None = None
    prompt_icon: str | None = None
    resource_ids: str | None = None  # JSON string of all resource IDs for merged notes
    exercise_ids: str | None = None  # JSON string of all exercise IDs for exercise-based notes


@router.post("/summary", response_model=dict)
async def generate_note_endpoint(
    request: NoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate or retrieve cached summary for a note"""

    # Enforce tier quotas
    enforce_quota_notes(current_user, db)

    # Resolve resource_id and resource_ids
    r_ids = request.resource_ids if request.resource_ids else []
    if not r_ids and request.resource_id:
        r_ids = [request.resource_id]

    e_ids = request.exercise_ids if request.exercise_ids else []

    if not r_ids and not e_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one resource or exercise must be provided",
        )

    primary_resource_id = r_ids[0] if r_ids else None

    # Verify resources belong to user
    resources = []
    if r_ids:
        resources = (
            db.query(Resource)
            .filter(Resource.id.in_(r_ids), Resource.user_id == current_user.id)
            .all()
        )

        if len(resources) != len(r_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="One or more resources not found"
            )

    # Verify exercises belong to user
    if e_ids:
        exercises = (
            db.query(Exercise)
            .filter(Exercise.id.in_(e_ids), Exercise.user_id == current_user.id)
            .all()
        )

        if len(exercises) != len(e_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="One or more exercises not found"
            )

    # Check for existing summary (only for single resource without exercises, to avoid cache clashes)
    if len(r_ids) == 1 and not e_ids and not request.force_regenerate and not request.custom_prompt:
        existing_summary = (
            db.query(Note)
            .filter(
                Note.resource_id == primary_resource_id,
                Note.summary_type == "summary",
                Note.processing_method == request.processing_method,
                Note.mode == request.mode,
                Note.output_format == request.output_format,
                Note.custom_prompt.is_(None),
                Note.processing_time_ms > 0,
                Note.file_path != "",
            )
            .order_by(Note.created_at.desc())
            .first()
        )

        if existing_summary:
            return {
                "resource_id": primary_resource_id,
                "title": existing_summary.title,
                "content": StorageManager.get_note_text(existing_summary.id) or "",
                "is_cached": True,
                "summary_type": existing_summary.summary_type,
                "quickread": StorageManager.get_note_text(existing_summary.id, is_quickread=True),
                "mode": existing_summary.mode or "elaborate",
                "output_format": existing_summary.output_format or "sentence",
                "processing_method": existing_summary.processing_method or "whole",
                "split_level": existing_summary.split_level,
                "processing_time": existing_summary.processing_time,
                "processing_time_ms": existing_summary.processing_time_ms,
                "model": existing_summary.model,
                "is_user_edited": existing_summary.is_user_edited or False,
                "id": existing_summary.id,
                "version": existing_summary.version,
                "custom_prompt": existing_summary.custom_prompt,
                "prompt_name": existing_summary.prompt_name,
                "prompt_icon": existing_summary.prompt_icon,
                "status": "completed",
                "exercise_ids": existing_summary.exercise_ids,
            }
    # If forcing regeneration, we simply bypass the cache check and generate a new one.

    import time

    from sqlalchemy import func

    from app.utils.db import generate_random_id

    doc_id = generate_random_id(db, Note)
    task_id = f"summary_{current_user.id}_{primary_resource_id or 'ex'}_{int(time.time())}"

    note_title = request.title
    if not note_title:
        if r_ids and e_ids:
            note_title = "Combined Note (Resources + Exercises)"
        elif r_ids:
            if len(r_ids) > 1:
                note_title = "Combined Note: " + ", ".join([r.title for r in resources[:3]])
                if len(resources) > 3:
                    note_title += "..."
            else:
                note_title = resources[0].title
        elif e_ids:
            ex_titles = [ex.title for ex in exercises]
            note_title = "Exercise Notes: " + ", ".join(ex_titles[:3])
            if len(ex_titles) > 3:
                note_title += "..."

    max_version = (
        db.query(func.max(Note.version)).filter(Note.resource_id == primary_resource_id).scalar()
        or 0
        if primary_resource_id
        else 0
    )
    next_version = max_version + 1

    import json

    doc = Note(
        id=doc_id,
        version=next_version,
        resource_id=primary_resource_id,
        user_id=current_user.id,
        title=note_title,
        summary_type="summary",
        file_path="",
        mode=request.mode,
        output_format=request.output_format,
        processing_method=request.processing_method,
        split_level=request.split_level,
        custom_prompt=request.custom_prompt,
        prompt_name=request.prompt_name,
        prompt_icon=request.prompt_icon,
        processing_time_ms=0,
        resource_ids=json.dumps(r_ids) if len(r_ids) > 1 else None,
        exercise_ids=json.dumps(e_ids) if e_ids else None,
    )
    db.add(doc)
    db.commit()

    TaskManager.submit_task(
        task_id,
        "note_generation",
        current_user.id,
        resource_id=primary_resource_id,
        resource_ids=r_ids,
        exercise_ids=e_ids,
        note_id=doc_id,
        title=note_title,
        mode=request.mode,
        output_format=request.output_format,
        processing_method=request.processing_method,
        split_level=request.split_level,
        custom_prompt=request.custom_prompt,
        prompt_name=request.prompt_name,
        prompt_icon=request.prompt_icon,
    )

    return {"task_id": task_id, "note_id": doc_id, "status": "pending"}


class GeneratePromptRequest(BaseModel):
    user_input: str


@router.post("/generate-prompt", response_model=dict)
async def generate_prompt(
    request: GeneratePromptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a custom prompt based on user's instruction"""
    ai_client = AIClient(user=current_user, db=db)
    system_instruction = "You are an expert prompt engineer. The user will give you instructions on how they want their study notes summarized. Your task is to output a JSON object with two keys: 'name' (a short, descriptive title for the template) and 'prompt' (a detailed, well-structured, multi-line instructional prompt that can be directly passed to another AI to generate the summary. Use line breaks `\\n` and clear formatting). Do NOT include any filler text or conversational intro. Output ONLY valid JSON, do not use markdown code blocks."
    prompt = f"User's request: {request.user_input}"

    try:
        generated_response = await ai_client.generate_text(
            prompt, max_tokens=1000, system_instruction=system_instruction
        )

        # Try to parse JSON from response
        import json

        # Clean up potential markdown formatting
        cleaned_text = generated_response.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]

        try:
            data = json.loads(cleaned_text.strip())
            return {"prompt": data.get("prompt", ""), "name": data.get("name", "")}
        except json.JSONDecodeError:
            # Fallback if AI didn't return valid JSON
            return {"prompt": generated_response.strip(), "name": "Generated Prompt"}
    except Exception as e:
        logger.error(f"Failed to generate prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate prompt: {e!s}",
        )


@router.post("/cheatsheet", response_model=CheatsheetResponse)
async def generate_cheatsheet(
    request: CheatsheetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate study cheatsheet from note"""

    # Enforce tier quotas
    enforce_quota_notes(current_user, db)

    # Verify note belongs to user
    note = (
        db.query(Resource)
        .filter(Resource.id == request.resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    note_content = StorageManager.get_note_text(note.id) or ""
    if not note_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource content not available yet. Please wait for processing.",
        )

    # Generate cheatsheet using AI
    ai_client = AIClient(current_user, db=db, category="processing")

    try:
        content = await ai_client.generate_summary(
            content=note_content, output_format=request.format
        )

        # Save generated summary
        doc_id = generate_random_id(db, Note)
        doc = Note(
            id=doc_id,
            resource_id=request.resource_id,
            title=f"Cheatsheet - {note.title}",
            summary_type="cheatsheet",
            file_path=f"cheatsheet_{note.id}.md",
        )
        db.add(doc)

        # Save to storage
        StorageManager.save_note_text(doc_id, content)

        db.commit()

        return CheatsheetResponse(
            resource_id=request.resource_id, title=f"Cheatsheet - {note.title}", content=content
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating cheatsheet: {e!s}",
        )


class UpdateNoteRequest(BaseModel):
    content: str
    title: str | None = None
    quickread: str | None = None


@router.put("/{note_id}", response_model=NoteItemResponse)
async def update_generated_note(
    note_id: str,
    request: UpdateNoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a generated summary (e.g. summary edit)"""
    doc = (
        db.query(Note)
        .outerjoin(Resource, Note.resource_id == Resource.id)
        .filter(
            Note.id == note_id,
            (Resource.user_id == current_user.id) | (Note.user_id == current_user.id),
        )
        .first()
    )

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Save to storage
    StorageManager.save_note_text(doc.id, request.content)
    if request.title:
        doc.title = request.title
    if request.quickread is not None:
        StorageManager.save_note_text(doc.id, request.quickread, is_quickread=True)

    # Mark as user edited
    doc.is_user_edited = True

    db.commit()
    db.refresh(doc)

    # Clear cache
    clear_cache_pattern_sync(f"cache_resp:/notes*:u{current_user.id}*")

    return NoteItemResponse(
        id=doc.id,
        version=doc.version,
        resource_id=doc.resource_id or "",
        note_id=doc.resource_id,
        title=doc.title,
        summary_type=doc.summary_type,
        file_path=doc.file_path,
        created_at=format_timestamp(doc.created_at),
        content=StorageManager.get_note_text(doc.id),
        quickread=StorageManager.get_note_text(doc.id, is_quickread=True),
        mode=doc.mode,
        output_format=doc.output_format,
        processing_method=doc.processing_method,
        split_level=doc.split_level,
        processing_time=doc.processing_time,
        processing_time_ms=doc.processing_time_ms,
        model=doc.model,
        is_user_edited=doc.is_user_edited,
        exercise_ids=doc.exercise_ids,
    )


@router.get("", response_model=list[NoteItemResponse])
async def list_notes(
    request: Request,
    resource_id: str | None = None,
    subject_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all generated summaries for current user"""
    query = (
        db.query(Note)
        .outerjoin(Resource, Note.resource_id == Resource.id)
        .filter((Resource.user_id == current_user.id) | (Note.user_id == current_user.id))
    )

    if subject_id:
        query = query.filter(Resource.subject_id == subject_id)
    if resource_id:
        query = query.filter(Note.resource_id == resource_id)

    summaries = query.all()

    return [
        NoteItemResponse(
            id=d.id,
            version=d.version,
            resource_id=d.resource_id,
            note_id=d.resource_id,
            title=d.title,
            summary_type=d.summary_type,
            file_path=d.file_path,
            created_at=format_timestamp(d.created_at),
            model=d.model,
            processing_time_ms=d.processing_time_ms,
            mode=d.mode,
            output_format=d.output_format,
            processing_method=d.processing_method,
            split_level=d.split_level,
            is_user_edited=d.is_user_edited or False,
            prompt_name=d.prompt_name,
            prompt_icon=d.prompt_icon,
            resource_ids=d.resource_ids,
            exercise_ids=d.exercise_ids,
        )
        for d in summaries
    ]


@router.get("/{note_id}", response_model=NoteItemResponse)
async def get_note(
    request: Request,
    note_id: str,
    resource_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific generated summary by ID or version (if resource_id provided)"""
    query = (
        db.query(Note)
        .outerjoin(Resource, Note.resource_id == Resource.id)
        .filter((Resource.user_id == current_user.id) | (Note.user_id == current_user.id))
    )

    if resource_id and note_id.startswith("v"):
        try:
            version_num = int(note_id[1:])
            summary = query.filter(
                Note.resource_id == resource_id, Note.version == version_num
            ).first()
        except ValueError:
            summary = None
    else:
        summary = query.filter(Note.id == note_id).first()

    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    return NoteItemResponse(
        id=summary.id,
        version=summary.version,
        resource_id=summary.resource_id,
        note_id=summary.resource_id,
        title=summary.title,
        summary_type=summary.summary_type,
        file_path=summary.file_path,
        created_at=format_timestamp(summary.created_at),
        content=StorageManager.get_note_text(summary.id),
        quickread=StorageManager.get_note_text(summary.id, is_quickread=True),
        mode=summary.mode,
        output_format=summary.output_format,
        processing_method=summary.processing_method,
        split_level=summary.split_level,
        processing_time=summary.processing_time,
        processing_time_ms=summary.processing_time_ms,
        model=summary.model,
        is_user_edited=summary.is_user_edited or False,
        prompt_name=summary.prompt_name,
        prompt_icon=summary.prompt_icon,
        resource_ids=summary.resource_ids,
        exercise_ids=summary.exercise_ids,
    )


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete a generated summary"""
    summary = (
        db.query(Note)
        .outerjoin(Resource, Note.resource_id == Resource.id)
        .filter(
            Note.id == note_id,
            (Resource.user_id == current_user.id) | (Note.user_id == current_user.id),
        )
        .first()
    )

    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Delete storage files
    StorageManager.delete_note_files(summary.id)

    db.delete(summary)
    db.commit()

    # Clear cache
    clear_cache_pattern_sync(f"cache_resp:/notes*:u{current_user.id}*")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{note_id}/rename")
async def rename_note(
    note_id: str,
    request: RenameNoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a generated summary"""
    summary = (
        db.query(Note)
        .outerjoin(Resource, Note.resource_id == Resource.id)
        .filter(
            Note.id == note_id,
            (Resource.user_id == current_user.id) | (Note.user_id == current_user.id),
        )
        .first()
    )

    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    summary.title = request.title
    summary.is_user_edited = True
    db.commit()

    # Clear cache
    clear_cache_pattern_sync(f"cache_resp:/notes*:u{current_user.id}*")

    return {"message": "Resource renamed", "title": summary.title}


@router.patch("/{note_id}/pin")
async def toggle_pin_note(
    note_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Toggle pin status of a summary"""
    summary = (
        db.query(Note)
        .outerjoin(Resource, Note.resource_id == Resource.id)
        .filter(
            Note.id == note_id,
            (Resource.user_id == current_user.id) | (Note.user_id == current_user.id),
        )
        .first()
    )

    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    summary.is_pinned = not summary.is_pinned
    db.commit()

    # Clear cache
    clear_cache_pattern_sync(f"cache_resp:/notes*:u{current_user.id}*")

    return {"message": "Resource pin toggled", "is_pinned": summary.is_pinned}


@router.post("/{note_id}/reprocess", response_model=dict)
def reprocess_note(
    note_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reprocess a failed generated note, re-submitting the generation task."""
    import json
    import time

    summary = (
        db.query(Note)
        .outerjoin(Resource, Note.resource_id == Resource.id)
        .filter(
            Note.id == note_id,
            (Resource.user_id == current_user.id) | (Note.user_id == current_user.id),
        )
        .first()
    )

    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    # Enforce tier quotas
    enforce_quota_notes(current_user, db)

    # Parse stored resource_ids / exercise_ids
    r_ids = json.loads(summary.resource_ids) if summary.resource_ids else []
    if not r_ids and summary.resource_id:
        r_ids = [summary.resource_id]
    e_ids = json.loads(summary.exercise_ids) if summary.exercise_ids else []

    if not r_ids and not e_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reprocess: missing resource or exercise references",
        )

    # Reset note state
    StorageManager.delete_note_files(summary.id)
    summary.file_path = ""
    summary.processing_time_ms = 0
    summary.model = None
    db.commit()

    task_id = f"summary_{current_user.id}_{r_ids[0] if r_ids else 'ex'}_{int(time.time())}"

    TaskManager.submit_task(
        task_id,
        "note_generation",
        current_user.id,
        resource_id=r_ids[0] if r_ids else None,
        resource_ids=r_ids,
        exercise_ids=e_ids,
        note_id=summary.id,
        title=summary.title,
        mode=summary.mode,
        output_format=summary.output_format,
        processing_method=summary.processing_method,
        split_level=summary.split_level,
        custom_prompt=summary.custom_prompt,
        prompt_name=summary.prompt_name,
        prompt_icon=summary.prompt_icon,
    )

    clear_cache_pattern_sync(f"cache_resp:/notes*:u{current_user.id}*")

    return {"task_id": task_id, "note_id": summary.id, "status": "pending"}


@router.post("/{note_id}/export", response_model=dict)
async def export_note(
    note_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export a specific generated summary as PDF or DOCX"""
    from pathlib import Path

    from app.models.db import ExportTemplate, Note, Resource
    from app.processing.text_processor import ContentSegment, ContentType

    # 1. Verify existence and ownership
    doc = (
        db.query(Note)
        .outerjoin(Resource, Note.resource_id == Resource.id)
        .filter(
            Note.id == note_id,
            (Resource.user_id == current_user.id) | (Note.user_id == current_user.id),
        )
        .first()
    )

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    note = (
        db.query(Resource).filter(Resource.id == doc.resource_id).first()
        if doc.resource_id
        else None
    )

    # 2. Extract options
    export_format = body.get("format", "pdf").lower()
    if export_format not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'docx'")

    template_id = body.get("template_id")
    template = None
    if template_id:
        template = db.query(ExportTemplate).filter(ExportTemplate.id == template_id).first()

    # 3. Build content segments
    segments = []

    # Add Quickread as a special section if it exists
    quickread = StorageManager.get_note_text(doc.id, is_quickread=True)
    if quickread:
        segments.append(
            ContentSegment(
                content=quickread,
                content_type=ContentType.H2,
                page_number=1,
                metadata={"title": "Quickread"},
            )
        )

    # Add the main content
    summary_text = StorageManager.get_note_text(doc.id) or ""
    segments.append(
        ContentSegment(
            content=summary_text,
            content_type=ContentType.BODY,
            page_number=1,
            metadata={"title": doc.title or "Resource"},
        )
    )

    # 4. Generate the summary
    from app.utils.paths import LEGACY_GENERATED_DIR
    output_dir = os.path.join(LEGACY_GENERATED_DIR, str(doc.resource_id))
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    safe_title = "".join(
        c for c in (doc.title or note.title) if c.isalnum() or c in (" ", "-", "_")
    ).strip()
    filename = f"{safe_title}_{uuid.uuid4().hex[:6]}.{export_format}"
    output_path = os.path.join(output_dir, filename)

    try:
        template_config = template.config if template else None

        if export_format == "pdf":
            from app.processing.document_generator import DocumentGenerator

            generator = DocumentGenerator(
                resource_id=doc.resource_id, note_title=note.title
            )
            temp_path = generator.generate_pdf(segments, [], template_config=template_config)
            import shutil

            shutil.move(temp_path, output_path)
        else:
            from app.processing.docx_generator import DocxGenerator

            generator = DocxGenerator(
                resource_id=doc.resource_id, note_title=note.title
            )
            temp_path = generator.generate_docx(segments, [], template_config=template_config)
            import shutil

            shutil.move(temp_path, output_path)

        # 5. Store export in Note as a permanent export record
        new_export = Note(
            id=generate_random_id(db, Note),
            resource_id=doc.resource_id,
            title=f"Export: {doc.title or 'Resource'} ({export_format.upper()})",
            file_path=output_path,
            summary_type=export_format,
            is_user_edited=False,
        )
        db.add(new_export)
        db.commit()

        return {
            "success": True,
            "message": f"{export_format.upper()} generated successfully",
            "download_url": f"/notes/{note_id}/download-export?export_id={new_export.id}",
            "filename": filename,
        }
    except Exception as e:
        import logging

        logger = logging.getLogger("app")
        logger.error(f"Error exporting summary {note_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting: {e!s}")


@router.get("/{note_id}/download-export")
async def download_note_export(
    note_id: str,
    export_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download a previously generated summary export"""


    from app.models.db import Note, Resource

    try:
        # Verify export summary exists and user owns the parent note
        export_doc = (
            db.query(Note)
            .outerjoin(Resource, Note.resource_id == Resource.id)
            .filter(
                Note.id == export_id,
                (Resource.user_id == current_user.id) | (Note.user_id == current_user.id),
            )
            .first()
        )

        if not export_doc:
            logger.error(
                f"[Download] Export doc {export_id} not found or unauthorized for user {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Exported record not found")

        if not os.path.exists(export_doc.file_path):
            logger.error(f"[Download] File not found on disk: {export_doc.file_path}")
            raise HTTPException(status_code=404, detail="Exported file not found on server")

        # Get original doc for title
        original_doc = db.query(Note).filter(Note.id == note_id).first()
        safe_title = "".join(
            c
            for c in ((original_doc.title if original_doc else "Resource") or "Resource")
            if c.isalnum() or c in (" ", "-", "_")
        ).strip()

        ext = export_doc.summary_type
        mime_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

        return FileResponse(
            path=export_doc.file_path,
            filename=f"{safe_title}.{ext}",
            media_type=mime_types.get(ext, "application/octet-stream"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Download] Internal error serving export {export_id}: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
