"""Notes management endpoints"""

import json
import logging
import os
import uuid
from datetime import datetime

import filetype
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from app.models.db import Exercise, Note, Resource, Subject, User
from app.processing.note_processor import (
    markdown_to_segments,
)
from app.processing.text_processor import ContentType
from app.schemas.schemas import ResourceResponse, ResourceUpdate
from app.utils.auth import get_current_user
from app.utils.cache import cache_response, clear_cache_pattern_sync
from app.utils.db import generate_random_id, get_db
from app.utils.quotas import enforce_quota_resources, enforce_quota_storage
from app.utils.storage import StorageManager
from app.utils.tasks import TaskManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceResponse])
@cache_response(ttl=3600)
async def get_resources(
    request: Request,
    subject_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all notes for the current user, optionally filtered by subject"""
    query = db.query(Resource).filter(Resource.user_id == current_user.id)

    if subject_id:
        query = query.filter(Resource.subject_id == subject_id)

    notes = query.order_by(Resource.created_at.desc()).all()

    response_notes = []
    for note in notes:
        note_data = ResourceResponse.from_orm(note)
        timings = StorageManager.get_resource_json(note.id, "timings")
        if timings:
            note_data.timings = timings
        response_notes.append(note_data)

    return response_notes


@router.post("/upload", response_model=list[ResourceResponse], status_code=status.HTTP_201_CREATED)
async def upload_resource(
    background_tasks: BackgroundTasks,
    subject_id: str = Form(...),
    files: list[UploadFile] = File(...),
    title: str = Form(None),
    use_ai_polish: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload multiple note files and create note records"""

    # Validate subject exists and belongs to user
    subject = (
        db.query(Subject)
        .filter(Subject.id == subject_id, Subject.user_id == current_user.id)
        .first()
    )

    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

    allowed_types = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "application/vnd.ms-powerpoint": ".ppt",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
    }

    processed_notes = []

    for file in files:
        # Handle auto-title per file
        auto_detect_title = False
        file_title = title
        if not file_title:
            file_title = os.path.splitext(file.filename)[0]
            auto_detect_title = True

        # If multiple files and a title is provided, use the filename as title instead of duplicating the same title
        if len(files) > 1 and title:
            file_title = f"{title} - {os.path.splitext(file.filename)[0]}"

        if file.content_type not in allowed_types:
            logger.warning(f"File type not allowed for {file.filename}: {file.content_type}")
            continue

        # Validate file size (50MB max)
        max_size = 50 * 1024 * 1024  # 50MB
        contents = await file.read()
        if len(contents) > max_size:
            logger.warning(f"File too large: {file.filename}")
            continue

        # Enforce tier quotas
        try:
            enforce_quota_resources(current_user, db)
            enforce_quota_storage(current_user, len(contents), db)
        except HTTPException as e:
            logger.error(f"Quota exceeded: {e.detail}")
            # If we already processed some, we return them, otherwise raise for the first one
            if not processed_notes:
                raise e
            break

        # Save file
        file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        file_path = StorageManager.get_upload_path(current_user.id, file_name)

        with open(file_path, "wb") as f:
            f.write(contents)

        # Create resource record
        db_note = Resource(
            id=generate_random_id(db, Resource),
            title=file_title,
            subject_id=subject_id,
            user_id=current_user.id,
            file_path=file_path,
            file_name=file.filename,
            file_size=len(contents),
            file_type=file.content_type,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(db_note)
        db.commit()
        db.refresh(db_note)

        # STEP 3: Process content extraction in background (Offloaded to Worker)
        task_id = f"ocr_{current_user.id}_{db_note.id}"
        TaskManager.submit_task(
            task_id,
            "resource_processing",
            current_user.id,
            resource_id=db_note.id,
            file_name=file.filename,
            auto_detect_title=auto_detect_title,
            use_ai_polish=use_ai_polish,
        )
        processed_notes.append(db_note)

    # Clear cache
    clear_cache_pattern_sync(f"cache_resp:/resources*:u{current_user.id}*")

    if not processed_notes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No valid files were uploaded"
        )

    return processed_notes


@router.get("/{resource_id}", response_model=ResourceResponse)
@cache_response(ttl=3600)
async def get_resource(
    request: Request,
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific note"""

    note = (
        db.query(Resource)
        .options(joinedload(Resource.subject).joinedload(Subject.group))
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    # Manually populate text fields from storage for the response
    note_data = ResourceResponse.from_orm(note)
    note_data.extracted_text = StorageManager.get_resource_text(resource_id)

    # Get structured content and images
    structured = StorageManager.get_resource_json(resource_id, "structured")
    if structured:
        note_data.extracted_content_structured = json.dumps(structured)

    images = StorageManager.get_resource_json(resource_id, "images")
    if images:
        note_data.extracted_images_metadata = json.dumps(images)

    timings = StorageManager.get_resource_json(resource_id, "timings")
    if timings:
        note_data.timings = timings

    logger.info(
        f"GET note {resource_id}: extracted_text length = {len(note_data.extracted_text) if note_data.extracted_text else 'NULL'}"
    )
    return note_data


@router.put("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: str,
    resource: ResourceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update resource metadata"""
    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if resource.title:
        note.title = resource.title

    if resource.subject_id:
        # Verify subject exists and belongs to user
        subject = (
            db.query(Subject)
            .filter(Subject.id == resource.subject_id, Subject.user_id == current_user.id)
            .first()
        )
        if not subject:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
        note.subject_id = resource.subject_id

    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)

    # Clear cache
    clear_cache_pattern_sync(f"cache_resp:/resources*:u{current_user.id}*")

    return note


@router.post("/{resource_id}/reprocess-ocr", response_model=ResourceResponse)
def reprocess_ocr(
    resource_id: str,
    use_v2: bool = True,
    use_ai_polish: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reprocess OCR for existing note to extract structured content with enhanced v2 processor"""

    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    try:
        logger.info(f"Reprocessing OCR for note {resource_id} (use_v2={use_v2}, use_ai_polish={use_ai_polish})")

        # Pre-task cleanup
        clear_cache_pattern_sync(f"cache_resp:/resources*:u{current_user.id}*")
        if note.output_pdf_path and os.path.exists(note.output_pdf_path):
            try:
                os.remove(note.output_pdf_path)
            except Exception:
                pass
        note.output_pdf_path = None
        note.processing_time_ms = None
        note.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(note)

        # Submit background task
        task_id = f"ocr_{current_user.id}_{note.id}"
        TaskManager.submit_task(
            task_id,
            "resource_processing",
            current_user.id,
            resource_id=note.id,
            file_name=note.title,
            auto_detect_title=False,
            use_ai_polish=use_ai_polish,
        )

        logger.info(f"Successfully submitted task for reprocessing OCR for note {resource_id}")

        note_data = ResourceResponse.from_orm(note)
        timings = StorageManager.get_resource_json(note.id, "timings")
        if timings:
            note_data.timings = timings

        return note_data

    except Exception as e:
        logger.error(f"Error submitting reprocessing task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reprocessing OCR: {e!s}",
        )


@router.post("/{resource_id}/reprocess", response_model=ResourceResponse)
def reprocess_resource_from_scratch(
    resource_id: str,
    use_v2: bool = True,
    use_ai_polish: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fully rebuild a note from the original uploaded file, replacing all derived content."""
    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    try:
        logger.info(f"Starting full resource rebuild for {resource_id} (use_ai_polish={use_ai_polish})")

        # Pre-task cleanup
        clear_cache_pattern_sync(f"cache_resp:/resources*:u{current_user.id}*")
        if note.output_pdf_path and os.path.exists(note.output_pdf_path):
            try:
                os.remove(note.output_pdf_path)
            except Exception:
                pass
        note.output_pdf_path = None
        note.processing_time_ms = None
        StorageManager.delete_resource_files(note.id)
        note.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(note)

        # Submit background task
        task_id = f"ocr_{current_user.id}_{note.id}"
        TaskManager.submit_task(
            task_id,
            "resource_processing",
            current_user.id,
            resource_id=note.id,
            file_name=note.title,
            auto_detect_title=True,
            use_ai_polish=use_ai_polish,
        )

        logger.info(f"Successfully submitted task for rebuilding note {resource_id} from scratch")

        note_data = ResourceResponse.from_orm(note)
        # Note: timings will be None since we deleted them above

        return note_data

    except Exception as e:
        logger.error(f"Error submitting resource rebuild task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rebuilding resource: {e!s}",
        )


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete a note"""
    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    # 1. Delete the actual uploaded file if it exists
    if note.file_path and os.path.exists(note.file_path):
        try:
            os.remove(note.file_path)
        except Exception as e:
            # Log error but don't fail the request
            logger.warning(f"Error deleting original file: {e}")

    # 2. Delete storage files (extracted text, structured JSON, images)
    try:
        StorageManager.delete_resource_files(note.id)
    except Exception as e:
        logger.warning(f"Error deleting storage files: {e}")

    # 3. Delete database record (cascades to related objects)
    try:
        db.delete(note)
        db.commit()

        # Clear cache
        clear_cache_pattern_sync(f"cache_resp:/resources*:u{current_user.id}*")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting note from database: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database deletion failed: {e!s}",
        )

    return None


@router.post("/{resource_id}/generate-pdf", response_model=dict)
async def generate_pdf(
    resource_id: str,
    body: dict | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate OUTPUT.pdf from note content"""

    # Get note
    if body is None:
        body = {}
    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    # Extract options from body
    include_toc = body.get("include_toc", True)
    include_cover = body.get("include_cover", True)

    try:
        # Build segments from structured content or markdown
        from app.processing.text_processor import ContentSegment

        segments = []
        images = []

        if note.extracted_content_structured:
            # Parse structured content
            structured_data = json.loads(note.extracted_content_structured)
            for item in structured_data:
                segment = ContentSegment(
                    content=item["content"],
                    content_type=ContentType(item["type"]),
                    page_number=item["page"],
                    confidence=item.get("confidence", 0.9),
                    metadata=item.get("metadata", {}),
                )
                segments.append(segment)
            # Images currently disabled - feature not yet implemented
        elif note.extracted_text:
            # Markdown-only: convert to segments
            structured_data = markdown_to_segments(note.extracted_text)
            for item in structured_data:
                segment = ContentSegment(
                    content=item["content"],
                    content_type=ContentType(item["type"]),
                    page_number=item.get("page", 1),
                    confidence=item.get("confidence", 0.9),
                    metadata=item.get("metadata", {}),
                )
                segments.append(segment)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Resource has no content to export. Please wait for processing to complete.",
            )

        # Actually generate the PDF
        from app.processing.document_generator import DocumentGenerator

        generator = DocumentGenerator(
            resource_id=note.id,
            note_title=note.title,
        )

        output_path = generator.generate_pdf(
            content_segments=segments,
            extracted_images=images,
            include_toc=include_toc,
            include_cover=include_cover,
        )

        # Save the output path
        note.output_pdf_path = output_path
        note.updated_at = datetime.utcnow()
        db.commit()

        logger.info(f"Generated PDF for note {resource_id}: {output_path}")

        return {
            "success": True,
            "message": "PDF generated successfully",
            "download_url": f"/resources/{resource_id}/download-pdf",
            "segments_count": len(segments),
            "images_count": len(images),
        }

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing structured content: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid structured content format"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error generating PDF: {e!s}"
        )


@router.get("/{resource_id}/download-pdf")
async def download_pdf(
    resource_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Download generated OUTPUT.pdf"""

    # Get note
    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if not note.output_pdf_path or not os.path.exists(note.output_pdf_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF not generated yet. Please generate it first.",
        )

    try:
        # Generate safe filename
        safe_title = "".join(c for c in note.title if c.isalnum() or c in (" ", "-", "_")).strip()
        filename = f"{safe_title}_OUTPUT.pdf"

        return FileResponse(
            path=note.output_pdf_path, filename=filename, media_type="application/pdf"
        )
    except Exception as e:
        logger.error(f"Error downloading PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error downloading PDF"
        )


@router.post("/{resource_id}/export", response_model=dict)
async def export_resource(
    resource_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export note as PDF or DOCX"""
    logger.info(f"[Export] Received request for note {resource_id} with body: {body}")
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Format must be 'pdf' or 'docx'"
        )

    include_cover = body.get("include_cover")
    template_id = body.get("template_id", None)

    # Load template config if provided
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
            logger.info(f"[Export] Loaded template '{tmpl.name}' (ID: {template_id})")
            logger.debug(
                f"[Export] Template Config Keys: {list(template_config.keys()) if template_config else 'None'}"
            )

            # Apply template settings for include_cover if not explicitly in request body
            if include_cover is None:
                include_cover = template_config.get("cover_page", {}).get("enabled", True)

            logger.info(f"[Export] Cover: {include_cover}")
        else:
            logger.warning(f"[Export] Template ID {template_id} not found in database")

    # Final defaults if still None
    if include_cover is None:
        include_cover = True

    # Get note
    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    # Build segments from structured content or markdown
    from app.processing.text_processor import ContentSegment, ContentType

    segments = []
    images = []  # Currently disabled - image feature not yet implemented

    try:
        # Inject header segments based on template config
        if template_config and "header" in template_config:
            h_cfg = template_config["header"]
            if h_cfg.get("show_note_title"):
                segments.append(
                    ContentSegment(
                        content=note.title, content_type=ContentType.NOTE_TITLE, page_number=1
                    )
                )
            if h_cfg.get("show_subject_name") and note.subject:
                segments.append(
                    ContentSegment(
                        content=note.subject.name,
                        content_type=ContentType.SUBJECT_NAME,
                        page_number=1,
                    )
                )
            if h_cfg.get("show_group_name") and note.subject and note.subject.group_id:
                from app.models.db import SubjectGroup

                group = (
                    db.query(SubjectGroup).filter(SubjectGroup.id == note.subject.group_id).first()
                )
                if group:
                    segments.append(
                        ContentSegment(
                            content=group.name, content_type=ContentType.GROUP_NAME, page_number=1
                        )
                    )

        # Flag to skip first H1 if we already injected a NOTE_TITLE
        skip_first_h1 = template_config and template_config.get("header", {}).get(
            "show_note_title", False
        )

        if note.extracted_content_structured:
            structured_data = json.loads(note.extracted_content_structured)
            for item in structured_data:
                # If it's the first H1 and we are skipping it, do so
                if skip_first_h1 and item["type"] == "h1":
                    skip_first_h1 = False  # Only skip the VERY first one
                    continue

                segment = ContentSegment(
                    content=item["content"],
                    content_type=ContentType(item["type"]),
                    page_number=item["page"],
                    confidence=item.get("confidence", 0.9),
                    metadata=item.get("metadata", {}),
                )
                segments.append(segment)
            # Images currently disabled - feature not yet implemented
        elif note.extracted_text:
            structured_data = markdown_to_segments(note.extracted_text)
            for item in structured_data:
                # If it's the first H1 and we are skipping it, do so
                if skip_first_h1 and item["type"] == "h1":
                    skip_first_h1 = False  # Only skip the VERY first one
                    continue

                segment = ContentSegment(
                    content=item["content"],
                    content_type=ContentType(item["type"]),
                    page_number=item.get("page", 1),
                    confidence=item.get("confidence", 0.9),
                    metadata=item.get("metadata", {}),
                )
                segments.append(segment)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Resource has no content to export. Please wait for processing to complete.",
            )

        # Generate the document
        "".join(c for c in note.title if c.isalnum() or c in (" ", "-", "_")).strip()

        if export_format == "pdf":
            from app.processing.document_generator import DocumentGenerator

            generator = DocumentGenerator(
                resource_id=note.id,
                note_title=note.title,
            )
            output_path = generator.generate_pdf(
                content_segments=segments,
                extracted_images=images,
                include_toc=False,
                include_cover=include_cover,
                template_config=template_config,
                progress_callback=progress_callback,
            )
            note.output_pdf_path = output_path
        else:
            from app.processing.docx_generator import DocxGenerator

            generator = DocxGenerator(
                resource_id=note.id,
                note_title=note.title,
            )
            output_path = generator.generate_docx(
                content_segments=segments,
                extracted_images=images,
                include_toc=False,
                include_cover=include_cover,
                template_config=template_config,
                progress_callback=progress_callback,
            )

        # Store in Note
        from app.models.db import Note

        gen_doc = Note(
            resource_id=note.id,
            title=f"{note.title} ({export_format.upper()})",
            file_path=output_path,
            summary_type=export_format,
        )
        db.add(gen_doc)
        note.updated_at = datetime.utcnow()
        db.commit()

        logger.info(f"Exported {export_format.upper()} for note {resource_id}: {output_path}")

        return {
            "success": True,
            "message": f"{export_format.upper()} generated successfully",
            "download_url": f"/resources/{resource_id}/download-export?format={export_format}",
            "task_id": task_id,
            "segments_count": len(segments),
            "images_count": len(images),
        }

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing structured content: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid structured content format"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting {export_format}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error exporting {export_format}: {e!s}",
        )


# In-memory export progress tracking
_export_progress = {}


@router.get("/{resource_id}/export-status/{task_id}")
async def get_export_status(
    resource_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get export task progress"""
    progress = _export_progress.get(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Task not found")
    return progress


@router.get("/{resource_id}/download-export")
async def download_export(
    resource_id: str,
    format: str = "pdf",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download generated export file (PDF or DOCX)"""

    export_format = format.lower()
    if export_format not in ("pdf", "docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Format must be 'pdf' or 'docx'"
        )

    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    # Look for the generated file
    from app.models.db import Note

    gen_doc = (
        db.query(Note)
        .filter(
            Note.resource_id == resource_id,
            Note.summary_type == export_format,
        )
        .order_by(Note.created_at.desc())
        .first()
    )

    if not gen_doc or not os.path.exists(gen_doc.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{export_format.upper()} not generated yet. Please generate it first.",
        )

    safe_title = "".join(c for c in note.title if c.isalnum() or c in (" ", "-", "_")).strip()

    mime_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    return FileResponse(
        path=gen_doc.file_path,
        filename=f"{safe_title}.{export_format}",
        media_type=mime_types[export_format],
    )


@router.put("/{resource_id}/content", response_model=ResourceResponse)
async def update_resource_content(
    resource_id: str,
    body: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save edited markdown content back to the note"""
    note = (
        db.query(Resource)
        .options(joinedload(Resource.subject))
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    new_text = body.get("extracted_text")
    if new_text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="extracted_text is required"
        )

    StorageManager.save_resource_text(note.id, new_text)
    StorageManager.save_resource_json(note.id, "structured", markdown_to_segments(new_text))
    note.updated_at = datetime.utcnow()

    # Invalidate existing summary when content changes
    db.query(Note).filter(Note.resource_id == resource_id, Note.summary_type == "summary").delete()

    db.commit()
    db.refresh(note)

    # Clear cache
    clear_cache_pattern_sync(f"cache_resp:/resources*:u{current_user.id}*")

    # Update embeddings to stay in sync
    if new_text and new_text.strip():
        def background_update_embeddings(res_id: str, txt: str):
            from app.processing.embeddings import update_resource_embeddings
            from app.utils.db import SessionLocal

            local_db = SessionLocal()
            try:
                update_resource_embeddings(res_id, txt, local_db)
                logger.info(f"Updated embeddings for note {res_id}")
            except Exception as e:
                logger.error(f"Error updating embeddings: {e}", exc_info=True)
            finally:
                local_db.close()

        background_tasks.add_task(background_update_embeddings, note.id, new_text)

    logger.info(f"Updated content for note {resource_id}: {len(new_text)} chars")
    return note


@router.get("/{resource_id}/download-file")
async def download_original_file(
    resource_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Download the original uploaded file"""
    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if not note.file_path or not os.path.exists(note.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original file not found")

    return FileResponse(
        path=note.file_path,
        filename=note.file_name or f"note_{resource_id}",
        media_type=note.file_type or "application/octet-stream",
    )


@router.get("/{resource_id}/processing-logs")
async def get_resource_processing_logs(
    resource_id: str,
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return recent log lines related to a specific note's processing.
    Scans api.log and errors.log for lines mentioning the resource_id.
    """
    note = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    import re

    from app.logging_config import LOGS_DIR

    # Include the per-entity process log first (most relevant, written by EntityLogHandler)
    per_entity_log = StorageManager.get_process_log(resource_id)

    # Scan global log files for any lines mentioning this resource_id
    log_files = ["processing.log", "worker.log", "backend.log", "errors.log"]
    entries = []

    for log_file in log_files:
        log_path = os.path.join(LOGS_DIR, log_file)
        if not os.path.exists(log_path):
            continue
        try:
            # Read last 5MB of each log file to avoid loading huge files
            max_bytes = 5 * 1024 * 1024
            with open(log_path, encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)
                file_size = f.tell()
                start = max(0, file_size - max_bytes)
                f.seek(start)
                if start > 0:
                    f.readline()  # skip partial first line
                lines = f.readlines()

            for line in lines:
                if resource_id not in line:
                    continue
                # Skip noisy uvicorn HTTP access lines for this note
                if "uvicorn.access" in line:
                    continue
                # Parse: "2026-06-22 17:10:03,378 [LEVEL] logger.name: message"
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
                            "timestamp": None,
                            "level": "INFO",
                            "logger": log_file,
                            "message": line.strip(),
                            "source": log_file,
                        }
                    )
        except Exception as e:
            logger.warning(f"Failed to read log file {log_file}: {e}")

    # Sort chronologically, trim to limit
    entries.sort(key=lambda x: x["timestamp"] or "")
    entries = entries[-limit:]

    return {
        "resource_id": resource_id,
        "count": len(entries),
        "entries": entries,
        "process_log": per_entity_log,
    }


@router.get("/{resource_id}/related")
def get_related_content(
    resource_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all notes and exercises related to a resource (direct + merged)"""
    try:
        resource = (
            db.query(Resource)
            .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
            .first()
        )
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")

        # Direct notes (resource_id matches)
        direct_notes = (
            db.query(Note)
            .join(Resource, Note.resource_id == Resource.id)
            .filter(Resource.user_id == current_user.id, Note.resource_id == resource_id)
            .order_by(Note.created_at.desc())
            .all()
        )

        # Merged notes (note's resource_ids JSON contains this resource_id)
        merged_notes = (
            db.query(Note)
            .join(Resource, Note.resource_id == Resource.id)
            .filter(
                Resource.user_id == current_user.id,
                Note.resource_id != resource_id,
                Note.resource_ids.isnot(None),
            )
            .order_by(Note.created_at.desc())
            .all()
        )
        merged_notes = [
            n for n in merged_notes if n.resource_ids and resource_id in json.loads(n.resource_ids)
        ]

        # Direct exercises
        direct_exercises = (
            db.query(Exercise)
            .filter(Exercise.user_id == current_user.id, Exercise.resource_id == resource_id)
            .order_by(Exercise.created_at.desc())
            .all()
        )

        # Merged exercises (check parameters JSON for resource_ids)
        from sqlalchemy import or_

        subject_exercises = (
            db.query(Exercise)
            .filter(
                Exercise.user_id == current_user.id,
                or_(Exercise.resource_id != resource_id, Exercise.resource_id.is_(None)),
                Exercise.subject_id == resource.subject_id,
            )
            .order_by(Exercise.created_at.desc())
            .all()
        )

        merged_exercises = []
        for ex in subject_exercises:
            params = StorageManager.get_resource_json(ex.id, "parameters")
            if params and isinstance(params, dict):
                r_ids = params.get("resource_ids", [])
                if resource_id in r_ids:
                    merged_exercises.append(ex)

        all_notes = direct_notes + merged_notes
        all_notes.sort(key=lambda n: n.created_at or datetime.min, reverse=True)

        all_exercises = direct_exercises + merged_exercises
        all_exercises.sort(key=lambda e: e.created_at or datetime.min, reverse=True)

        def format_timestamp(dt):
            if not dt:
                return ""
            if dt.tzinfo is None:
                return dt.isoformat() + "Z"
            return dt.isoformat()

        notes_data = []
        for n in all_notes:
            notes_data.append(
                {
                    "id": n.id,
                    "version": n.version,
                    "resource_id": n.resource_id,
                    "title": n.title,
                    "summary_type": n.summary_type,
                    "file_path": n.file_path,
                    "created_at": format_timestamp(n.created_at),
                    "mode": n.mode,
                    "output_format": n.output_format,
                    "processing_method": n.processing_method,
                    "split_level": n.split_level,
                    "model": n.model,
                    "is_user_edited": n.is_user_edited or False,
                    "is_pinned": n.is_pinned or False,
                    "prompt_name": n.prompt_name,
                    "prompt_icon": n.prompt_icon,
                    "resource_ids": n.resource_ids,
                }
            )

        exercises_data = []
        for ex in all_exercises:
            params = StorageManager.get_resource_json(ex.id, "parameters") or {}
            exercises_data.append(
                {
                    "id": ex.id,
                    "title": ex.title,
                    "resource_id": ex.resource_id,
                    "subject_id": ex.subject_id,
                    "group_id": ex.group_id,
                    "file_path": ex.file_path,
                    "file_name": ex.file_name,
                    "model": ex.model,
                    "processing_time_ms": ex.processing_time_ms,
                    "created_at": format_timestamp(ex.created_at),
                    "updated_at": format_timestamp(ex.updated_at),
                    "parameters": params,
                }
            )

        return {
            "notes": notes_data,
            "exercises": exercises_data,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching related content for resource {resource_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{resource_id}/images/{image_path:path}")
def serve_resource_image(
    resource_id: str,
    image_path: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Serve an extracted image for a resource."""
    resource = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    safe_path = os.path.basename(image_path)
    full_path = os.path.join(
        StorageManager.get_extracted_images_dir(current_user.id, resource_id), safe_path
    )

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(full_path)

@router.post("/{resource_id}/upload-image")
async def upload_resource_image(
    resource_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resource = db.query(Resource).filter(Resource.id == resource_id, Resource.user_id == current_user.id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")

    kind = filetype.guess(contents)
    if not kind or not kind.mime.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid image file")

    if kind.mime in ["image/gif", "image/svg+xml"]:
        raise HTTPException(status_code=400, detail="GIF and SVG formats are not allowed")

    upload_dir = StorageManager.get_user_images_dir(current_user.id, resource_id)

    ext = kind.extension

    # Process and compress image using PIL
    import io

    from PIL import Image

    try:
        img = Image.open(io.BytesIO(contents))
        if img.mode == 'P':
            img = img.convert('RGBA')
        elif img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGBA')

        # Max dimensions to prevent massive resolutions
        max_size = (1920, 1080)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Save compressed as webp
        filename = f"img_{uuid.uuid4().hex}.webp"
        filepath = os.path.join(upload_dir, filename)
        img.save(filepath, 'WEBP', quality=80, method=6)
    except Exception as e:
        logger.error(f"Image compression failed: {e}")
        # Fallback to original if processing fails
        filename = f"img_{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as f:
            f.write(contents)

    return {"url": f"/api/resources/{resource_id}/user-images/{filename}"}


@router.get("/{resource_id}/user-images/{image_path:path}")
def serve_user_image(
    resource_id: str,
    image_path: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from fastapi.responses import FileResponse
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    has_access = False
    if resource.user_id == current_user.id:
        has_access = True
    elif resource.subject_id:
        from app.models.db import GroupMember, Subject
        subject = db.query(Subject).filter(Subject.id == resource.subject_id).first()
        if subject and subject.group_id:
            member = db.query(GroupMember).filter(
                GroupMember.group_id == subject.group_id,
                GroupMember.user_id == current_user.id
            ).first()
            if member:
                has_access = True

    if not has_access:
        raise HTTPException(status_code=403, detail="Not authorized to access this resource")

    safe_path = os.path.basename(image_path)
    full_path = os.path.join(
        StorageManager.get_user_images_dir(resource.user_id, resource_id), safe_path
    )

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(full_path)
