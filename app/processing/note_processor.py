import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.models.db import Resource, Task, User
from app.processing.smart_pipeline import SmartPipeline
from app.processing.unified_processor import UnifiedContentProcessor
from app.utils.cache import clear_cache_pattern_sync
from app.utils.db import SessionLocal
from app.utils.storage import StorageManager
from app.utils.tasks import TaskManager

logger = logging.getLogger(__name__)


def _log(msg: str):
    """Single-line helper so all task log lines have a consistent prefix."""
    logger.info(msg)


def get_pipeline_for_user(user: User) -> SmartPipeline:
    """Get a SmartPipeline instance with the appropriate settings for this user."""
    from app.config import get_settings

    app_settings = get_settings()

    # Determine whether we have any AI tier available for the polish pass.
    # We only pass a gemini_api_key if the configured Tier 1 provider is actually Gemini
    # so that smart_pipeline.py does not try to use a Groq/HF key as a Gemini credential.
    tier1_provider = getattr(app_settings, "GLOBAL_AI_TIER1_PROVIDER", "gemini").lower()
    tier1_api_key = getattr(app_settings, "GLOBAL_AI_TIER1_API_KEY", None)

    # Gemini-specific key (for the SmartPipeline's gemini_api_key parameter)
    gemini_key = None
    if tier1_provider == "gemini":
        gemini_key = tier1_api_key or app_settings.GEMINI_API_KEY
    else:
        # Fall back to explicit GEMINI_API_KEY if set separately
        gemini_key = getattr(app_settings, "GEMINI_API_KEY", None) or None

    gemini_model = app_settings.GLOBAL_AI_TIER1_MODEL

    if not getattr(user, "use_global_ai_config", False):
        if getattr(user, "ai_model", None):
            gemini_model = user.ai_model

    # Enable polish if any tier key is present (Gemini, Groq, etc.)
    has_any_ai_key = bool(tier1_api_key) or bool(gemini_key)

    return SmartPipeline(
        use_polish=has_any_ai_key,
        gemini_api_key=gemini_key,  # May be None for non-Gemini providers — polish still works via AIClient tiers
        gemini_model=gemini_model,
    )


def get_unified_processor_for_user(
    user: User, use_polish: bool = False
) -> UnifiedContentProcessor:
    """Get a UnifiedContentProcessor with the appropriate settings for this user.
    Defaults to use_polish=False for fast, layout-preserved, zero-RAM extraction.
    """
    from app.config import get_settings

    app_settings = get_settings()

    tier1_provider = getattr(app_settings, "GLOBAL_AI_TIER1_PROVIDER", "gemini").lower()
    tier1_api_key = getattr(app_settings, "GLOBAL_AI_TIER1_API_KEY", None)
    gemini_key = None
    if tier1_provider == "gemini":
        gemini_key = tier1_api_key or app_settings.GEMINI_API_KEY
    else:
        gemini_key = getattr(app_settings, "GEMINI_API_KEY", None) or None
    gemini_model = app_settings.GLOBAL_AI_TIER1_MODEL

    if not getattr(user, "use_global_ai_config", False):
        if getattr(user, "ai_model", None):
            gemini_model = user.ai_model

    return UnifiedContentProcessor(
        use_polish=use_polish,
        gemini_api_key=gemini_key,
        gemini_model=gemini_model,
    )


def ensure_valid_markdown_result(markdown: str) -> str:
    """
    SmartPipeline returns an error string on failure; treat that as a real failure
    """
    if isinstance(markdown, str) and markdown.startswith("Error:"):
        raise RuntimeError(markdown)
    return markdown


def extract_markdown_for_user(
    user: User, file_path: str, progress_callback: Callable | None = None
) -> tuple:
    """
    Process a resource with the configured SmartPipeline.
    """
    pipeline = get_pipeline_for_user(user)
    try:
        markdown = ensure_valid_markdown_result(
            pipeline.process(file_path, progress_callback=progress_callback)
        )
        return markdown, getattr(pipeline, "timings", {})
    except Exception:
        if not getattr(pipeline, "use_polish", False):
            raise

        logger.warning(
            f"Smart pipeline with AI polish failed for {file_path}; retrying with local extraction only",
            exc_info=True,
        )
        fallback_pipeline = SmartPipeline(use_polish=False)
        markdown = ensure_valid_markdown_result(
            fallback_pipeline.process(file_path, progress_callback=progress_callback)
        )
        return markdown, getattr(fallback_pipeline, "timings", {})


def markdown_to_segments(markdown: str) -> list:
    """
    Convert Markdown text to structured segments compatible with the existing resource view UI.
    """
    import re

    segments = []
    page = 1

    for line in markdown.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Determine content type
        if stripped.startswith("# "):
            content_type = "h1"
            content = stripped[2:]
        elif stripped.startswith("## "):
            content_type = "h2"
            content = stripped[3:]
        elif stripped.startswith("### "):
            content_type = "h3"
            content = stripped[4:]
        elif stripped.startswith("#### "):
            content_type = "h4"
            content = stripped[5:]
        elif stripped.startswith("##### "):
            content_type = "h5"
            content = stripped[6:]
        elif stripped.startswith("- "):
            content_type = "list"
            content = stripped[2:]
        elif re.match(r"^\d+\.\s", stripped):
            content_type = "ordered_list"
            content = re.sub(r"^\d+\.\s", "", stripped)
        elif stripped.startswith("|"):
            content_type = "table_row"
            content = stripped
        elif stripped.startswith("|---"):
            continue  # Skip table separator rows
        else:
            content_type = "body"
            content = stripped

        segments.append(
            {
                "content": content,
                "type": content_type,
                "page": page,
                "confidence": 0.95,
                "metadata": {"source": "smart_pipeline"},
            }
        )

    return segments


def process_resource_task(
    resource_id: str,
    user_id: int,
    auto_detect_title: bool = False,
    use_ai_polish: bool = False,
    **kwargs,
):
    """Core logic to process a resource, used by both worker and (optionally) API."""
    task_id = kwargs.get("task_id") or f"ocr_{user_id}_{resource_id}"
    started_at = datetime.now(timezone.utc).isoformat()
    # Support both use_ai_polish and use_polish keyword arguments
    effective_polish = bool(kwargs.get("use_polish", use_ai_polish))

    db = SessionLocal()
    try:
        resource = db.query(Resource).filter(Resource.id == resource_id).first()
        user = db.query(User).filter(User.id == user_id).first()

        if not resource or not user:
            logger.error(
                f"[{resource_id}] Processing failed: Resource or User {user_id} not found in DB"
            )
            TaskManager._update_db_task(
                task_id, status="failed", error="Resource or User not found"
            )
            return {"status": "error", "message": "Resource or User not found"}

        # ── Header banner ──────────────────────────────────────────────────────
        file_path = resource.file_path
        file_size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        file_ext = Path(file_path).suffix.lower()
        _log(
            f"[{resource_id}] ══════════════════════════════════════════════════════"
        )
        _log(f"[{resource_id}] RESOURCE PROCESSING START")
        _log(f"[{resource_id}]   task_id       : {task_id}")
        _log(f"[{resource_id}]   started_at    : {started_at}")
        _log(f"[{resource_id}]   user_id       : {user_id}  (email: {user.email})")
        _log(f"[{resource_id}]   resource_id   : {resource_id}")
        _log(f"[{resource_id}]   title         : {resource.title}")
        _log(f"[{resource_id}]   file_path     : {file_path}")
        _log(f"[{resource_id}]   file_type     : {resource.file_type}  ext: {file_ext}")
        _log(f"[{resource_id}]   file_size     : {file_size_bytes:,} bytes ({file_size_bytes / 1024:.1f} KB)")
        _log(f"[{resource_id}]   auto_detect   : {auto_detect_title}")
        _log(f"[{resource_id}]   use_ai_polish : {effective_polish}")
        _log(
            f"[{resource_id}] ══════════════════════════════════════════════════════"
        )

        def is_cancelled():
            try:
                check_db = SessionLocal()
                t = check_db.query(Task).filter(Task.task_id == task_id).first()
                cancelled = t and (t.status == "failed" or t.status == "cancelled")
                check_db.close()
                return cancelled
            except Exception:
                return False

        if is_cancelled():
            _log(f"[{resource_id}] Task aborted before start (status=cancelled in DB)")
            return {"status": "cancelled"}

        if not os.path.exists(file_path):
            logger.error(f"[{resource_id}] File not found on disk: {file_path}")
            TaskManager._update_db_task(task_id, status="failed", error="File not found on disk")
            return {"status": "error", "message": "File not found on disk"}

        def progress_callback(percent, message=None):
            TaskManager.update_task_progress(task_id, percent, message=message)

        start_time = time.time()
        last_pipeline_pct = [0]

        def pipeline_callback(p, message=None):
            if is_cancelled():
                raise InterruptedError("Task cancelled by user")
            msg = message or "Extracting text..."
            if p > 30 and not message:
                msg = "Analyzing document structure..."
            if p > 60 and not message:
                msg = "Polishing with AI..."
            if p > 85 and not message:
                msg = "Finalizing content..."
            # Log each significant step change (≥10% jump)
            if p - last_pipeline_pct[0] >= 10:
                elapsed = time.time() - start_time
                _log(f"[{resource_id}] Pipeline progress {p:3d}% (+{elapsed:.1f}s): {msg}")
                last_pipeline_pct[0] = p
            progress_callback(p, msg)

        # ── Extraction ─────────────────────────────────────────────────────────
        _log(f"[{resource_id}] Starting UnifiedContentProcessor.extract()")
        try:
            processor = get_unified_processor_for_user(user, use_polish=effective_polish)
            _log(f"[{resource_id}]   use_polish    : {processor.use_polish}")
            _log(f"[{resource_id}]   gemini_model  : {processor.gemini_model or 'none'}")
            bundle = processor.extract(
                file_path, resource_id=resource.id, progress_callback=pipeline_callback
            )
        except InterruptedError:
            _log(f"[{resource_id}] Task halted during extraction (user cancelled)")
            return {"status": "cancelled"}

        extraction_elapsed = time.time() - start_time
        markdown = bundle.markdown
        markdown_len = len(markdown) if markdown else 0
        image_count = len(bundle.images) if bundle.images else 0
        image_refs_in_md = markdown.count("![" ) if markdown else 0

        _log(f"[{resource_id}] Extraction complete in {extraction_elapsed:.2f}s")
        _log(f"[{resource_id}]   processing_path : {bundle.processing_path}")
        _log(f"[{resource_id}]   markdown_chars  : {markdown_len:,}")
        _log(f"[{resource_id}]   images_extracted: {image_count}")
        _log(f"[{resource_id}]   image_refs_in_md: {image_refs_in_md}")
        if bundle.timings:
            for step, t in bundle.timings.items():
                _log(f"[{resource_id}]   timing/{step:<22}: {t:.3f}s")
        if bundle.warnings:
            for w in bundle.warnings:
                logger.warning(f"[{resource_id}] Pipeline warning: {w}")

        # ── Segment parsing ────────────────────────────────────────────────────
        _log(f"[{resource_id}] Parsing markdown into structured segments...")
        structured_segments = markdown_to_segments(markdown)
        _log(f"[{resource_id}]   segments_count  : {len(structured_segments)}")

        # ── File saves ─────────────────────────────────────────────────────────
        _log(f"[{resource_id}] Saving output files...")

        md_path = StorageManager._get_resource_path(resource.id)
        StorageManager.save_resource_text(resource.id, markdown)
        _log(f"[{resource_id}]   SAVED markdown      → {md_path}  ({markdown_len:,} chars)")

        structured_path = StorageManager._get_resource_json_path(resource.id, "structured")
        StorageManager.save_resource_json(resource.id, "structured", structured_segments)
        _log(f"[{resource_id}]   SAVED structured    → {structured_path}  ({len(structured_segments)} segments)")

        timings_path = StorageManager._get_resource_json_path(resource.id, "timings")
        StorageManager.save_resource_json(resource.id, "timings", bundle.timings)
        _log(f"[{resource_id}]   SAVED timings       → {timings_path}")

        if bundle.images:
            images_data = [
                img.to_dict() if hasattr(img, "to_dict") else img for img in bundle.images
            ]
            images_path = StorageManager._get_resource_json_path(resource.id, "images")
            StorageManager.save_resource_json(resource.id, "images", images_data)
            _log(f"[{resource_id}]   SAVED images meta   → {images_path}  ({len(images_data)} images)")

            image_map_path = StorageManager._get_resource_json_path(resource.id, "image_map")
            StorageManager.save_resource_json(resource.id, "image_map", bundle.image_map)
            _log(f"[{resource_id}]   SAVED image_map     → {image_map_path}")

            # Log each extracted image file path
            for img in bundle.images:
                img_file = img.file_path if hasattr(img, "file_path") else img.get("file_path", "")
                img_id = img.id if hasattr(img, "id") else img.get("id", "?")
                is_dec = img.is_decorative if hasattr(img, "is_decorative") else img.get("is_decorative", False)
                if img_file and not is_dec:
                    _log(f"[{resource_id}]   IMAGE [{img_id}] → {img_file}")
        else:
            _log(f"[{resource_id}]   No images extracted for this resource")

        # ── Title detection ────────────────────────────────────────────────────
        if auto_detect_title:
            for line in markdown.split("\n"):
                if line.strip().startswith("# "):
                    detected_title = line.strip()[2:].strip()
                    if detected_title:
                        _log(f"[{resource_id}]   Auto-detected title: '{detected_title}'")
                        resource.title = detected_title
                        break

        total_elapsed = time.time() - start_time
        resource.processing_time_ms = int(total_elapsed * 1000)
        resource.updated_at = datetime.utcnow()
        db.commit()
        _log(f"[{resource_id}] DB record updated (processing_time_ms={resource.processing_time_ms})")

        # ── Embeddings ─────────────────────────────────────────────────────────
        if markdown and markdown.strip():
            if is_cancelled():
                _log(f"[{resource_id}] Task halted before embeddings (user cancelled)")
                return {"status": "cancelled"}
            try:
                progress_callback(95, "Generating search embeddings...")
                _log(f"[{resource_id}] Generating search embeddings...")
                from app.processing.embeddings import update_resource_embeddings
                embed_start = time.time()
                update_resource_embeddings(resource.id, markdown, db)
                _log(f"[{resource_id}]   Embeddings done in {time.time() - embed_start:.2f}s")
            except Exception as e:
                logger.error(f"[{resource_id}] Error updating embeddings: {e}", exc_info=True)

        # ── Completion banner ──────────────────────────────────────────────────
        TaskManager._update_db_task(task_id, status="completed", progress=100, message="Completed")
        _log(
            f"[{resource_id}] ══════════════════════════════════════════════════════"
        )
        _log(f"[{resource_id}] RESOURCE PROCESSING COMPLETE")
        _log(f"[{resource_id}]   total_time      : {total_elapsed:.2f}s")
        _log(f"[{resource_id}]   markdown_chars  : {markdown_len:,}")
        _log(f"[{resource_id}]   segments        : {len(structured_segments)}")
        _log(f"[{resource_id}]   images          : {image_count}")
        _log(f"[{resource_id}]   path            : {bundle.processing_path}")
        _log(
            f"[{resource_id}] ══════════════════════════════════════════════════════"
        )
        clear_cache_pattern_sync(f"cache_resp:/resources*:u{user.id}*")
        return {"status": "success", "resource_id": resource_id}

    except Exception as e:
        if "Task cancelled by user" in str(e):
            _log(f"[{resource_id}] Task confirmed cancelled")
            return {"status": "cancelled"}
        logger.error(f"[{resource_id}] FATAL error in processing: {e}", exc_info=True)
        TaskManager._update_db_task(task_id, status="failed", error=str(e))
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
