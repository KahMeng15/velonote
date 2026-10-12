"""Semantic search endpoints"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.db import Exercise, Note, Resource, Subject, Task, User
from app.utils.auth import get_current_user
from app.utils.db import get_db
from app.utils.storage import StorageManager

router = APIRouter(prefix="/search", tags=["search"])


# Lazy import to avoid version conflicts at startup
def get_embeddings_manager():
    try:
        from app.processing.search import EmbeddingsManager

        return EmbeddingsManager()
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Search service unavailable: {e!s}",
        )


class SearchQuery(BaseModel):
    query: str
    resource_id: str = None
    top_k: int = 5


class SearchResult(BaseModel):
    content: str
    score: float
    resource_id: str
    resource_title: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total_results: int


@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    request: SearchQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Perform semantic search across user's resources
    """
    try:
        # Get resources to search
        if request.resource_id:
            resources = (
                db.query(Resource)
                .filter(Resource.id == request.resource_id, Resource.user_id == current_user.id)
                .all()
            )
        else:
            resources = db.query(Resource).filter(Resource.user_id == current_user.id).all()

        if not resources:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No resources found to search"
            )

        # Collect all chunks from resources
        all_chunks = []
        chunk_metadata = []  # Track which resource each chunk comes from

        for resource in resources:
            text = StorageManager.get_resource_text(resource.id)
            if not text:
                continue

            # Split resource content into chunks
            from app.processing.ocr import OCRProcessor

            chunks = OCRProcessor.chunk_text(text)

            for chunk in chunks:
                all_chunks.append(chunk)
                chunk_metadata.append(
                    {"resource_id": resource.id, "resource_title": resource.title, "content": chunk}
                )

        if not all_chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No text content available in resources for search",
            )

        # Perform semantic search
        embeddings_mgr = get_embeddings_manager()
        results = embeddings_mgr.search(
            query=request.query, documents=all_chunks, top_k=request.top_k
        )

        # Build response
        search_results = []
        for chunk, score in results:
            # Find metadata for this chunk
            for metadata in chunk_metadata:
                if metadata["content"] == chunk:
                    search_results.append(
                        SearchResult(
                            content=chunk,
                            score=float(score),
                            resource_id=metadata["resource_id"],
                            resource_title=metadata["resource_title"],
                        )
                    )
                    break

        return SearchResponse(
            query=request.query, results=search_results, total_results=len(search_results)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Search error: {e!s}"
        )


@router.get("/similar/{resource_id}")
async def get_similar_resources(
    resource_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Find similar resources based on content similarity
    """
    try:
        # Get source resource
        source_resource = (
            db.query(Resource)
            .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
            .first()
        )

        source_text = StorageManager.get_resource_text(resource_id)
        if not source_resource or not source_text:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found or has no content"
            )

        # Get all other resources
        other_resources = (
            db.query(Resource)
            .filter(Resource.user_id == current_user.id, Resource.id != resource_id)
            .all()
        )

        # Filter for resources that actually have text on disk
        valid_other_resources = []
        other_contents = []
        for l in other_resources:
            text = StorageManager.get_resource_text(l.id)
            if text:
                valid_other_resources.append(l)
                other_contents.append(text[:1000])

        if not valid_other_resources:
            return {"similar_resources": []}

        # Extract first chunk from source resource as query
        from app.processing.ocr import OCRProcessor

        source_chunks = OCRProcessor.chunk_text(source_text)

        if not source_chunks:
            return {"similar_resources": []}

        source_chunk = source_chunks[0]

        # Search for similar content
        embeddings_mgr = get_embeddings_manager()

        results = embeddings_mgr.search(query=source_chunk, documents=other_contents, top_k=5)

        similar_resources = []
        for content, score in results:
            for i, text_snippet in enumerate(other_contents):
                if text_snippet.startswith(content[:500]):
                    l = valid_other_resources[i]
                    similar_resources.append(
                        {
                            "id": l.id,
                            "title": l.title,
                            "similarity_score": float(score),
                            "subject_id": l.subject_id,
                        }
                    )
                    break

        return {"similar_resources": similar_resources}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding similar resources: {e!s}",
        )


@router.get("/tasks/active")
async def get_active_tasks(current_user: User = Depends(get_current_user)):
    """Get all currently processing tasks for the user"""
    from app.utils.tasks import TaskManager

    tasks = TaskManager.get_active_tasks(current_user.id)
    return {"tasks": tasks}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, current_user: User = Depends(get_current_user)):
    """Cancel a background processing task"""
    from app.utils.tasks import TaskManager

    success = TaskManager.cancel_task(task_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Task not found or already finished"
        )
    return {"status": "cancelled"}


@router.post("/tasks/{task_id}/dismiss")
async def dismiss_task(
    task_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Dismiss a background processing task (removes it from DB)"""
    from app.models.db import Task

    task = db.query(Task).filter(Task.task_id == task_id, Task.user_id == current_user.id).first()
    if task:
        db.delete(task)
        db.commit()
    return {"status": "dismissed"}


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, current_user: User = Depends(get_current_user)):
    """Get status of a background processing task"""
    from app.utils.tasks import TaskManager

    status_info = TaskManager.get_task_status(task_id, user_id=current_user.id)

    if not status_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return status_info


@router.get("/task")
async def get_resource_or_exercise_task_status(
    resource_id: str | None = None,
    exercise_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a background processing task for a resource or exercise.
    Never 404s — returns a sensible default status instead."""
    import logging

    logger = logging.getLogger(__name__)

    if resource_id:
        return _get_resource_task_status(resource_id, current_user, db, logger)
    elif exercise_id:
        return _get_exercise_task_status(exercise_id, current_user, db, logger)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either resource_id or exercise_id",
        )


def _get_resource_task_status(resource_id: str, current_user, db, logger):
    """Get status of OCR task for a resource (extracted for reuse)"""
    resource = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not resource:
        logger.warning(f"Resource {resource_id} not found for user {current_user.id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    task_id_pattern = f"ocr_{current_user.id}_{resource_id}%"
    db_task = (
        db.query(Task)
        .filter(Task.user_id == current_user.id, Task.task_id.like(task_id_pattern))
        .order_by(Task.updated_at.desc())
        .first()
    )

    if db_task:
        return {
            "task_id": db_task.task_id,
            "status": db_task.status,
            "progress": db_task.progress or 0,
            "updated_at": db_task.updated_at.isoformat() if db_task.updated_at else None,
            "error": db_task.error_message,
        }

    has_text = bool(StorageManager.get_resource_text(resource.id))
    if has_text:
        return {"task_id": None, "status": "completed", "progress": 100}
    else:
        return {"task_id": None, "status": "pending", "progress": 0}


def _get_exercise_task_status(exercise_id: str, current_user, db, logger):
    """Get status of extraction/generation task for an exercise. Never 404s."""
    exercise = (
        db.query(Exercise)
        .filter(Exercise.id == exercise_id, Exercise.user_id == current_user.id)
        .first()
    )

    if not exercise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")

    for prefix in ("extract_", "generate_"):
        db_task = (
            db.query(Task)
            .filter(
                Task.user_id == current_user.id,
                Task.task_id == f"{prefix}{exercise_id}",
            )
            .order_by(Task.updated_at.desc())
            .first()
        )
        if db_task:
            return {
                "task_id": db_task.task_id,
                "status": db_task.status,
                "progress": db_task.progress or 0,
                "updated_at": db_task.updated_at.isoformat() if db_task.updated_at else None,
                "error": db_task.error_message,
            }

    has_questions = bool(exercise.content_path)
    if has_questions:
        return {"task_id": None, "status": "completed", "progress": 100}
    else:
        return {"task_id": None, "status": None, "progress": 0}


class RecentItem(BaseModel):
    id: str
    type: str
    title: str
    updated_at: str
    subject_id: str | None = None
    subject_name: str | None = None


@router.get("/recent", response_model=list[RecentItem])
def get_recent_items(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get recent items (resources, exercises, notes) for the current user"""
    resources = (
        db.query(Resource)
        .filter(Resource.user_id == current_user.id)
        .order_by(Resource.updated_at.desc())
        .limit(10)
        .all()
    )

    exercises = (
        db.query(Exercise)
        .filter(Exercise.user_id == current_user.id)
        .order_by(Exercise.updated_at.desc())
        .limit(10)
        .all()
    )

    notes = (
        db.query(Note)
        .join(Resource, Note.resource_id == Resource.id)
        .filter(Resource.user_id == current_user.id)
        .order_by(Note.created_at.desc())
        .limit(10)
        .all()
    )

    subjects = {
        s.id: s.name for s in db.query(Subject).filter(Subject.user_id == current_user.id).all()
    }

    items: list[RecentItem] = []

    for r in resources:
        items.append(
            RecentItem(
                id=r.id,
                type="resource",
                title=r.title,
                updated_at=r.updated_at.isoformat() if r.updated_at else "",
                subject_id=r.subject_id,
                subject_name=subjects.get(r.subject_id),
            )
        )

    for e in exercises:
        items.append(
            RecentItem(
                id=e.id,
                type="exercise",
                title=e.title,
                updated_at=e.updated_at.isoformat() if e.updated_at else "",
                subject_id=e.subject_id,
                subject_name=subjects.get(e.subject_id),
            )
        )

    for n in notes:
        items.append(
            RecentItem(
                id=n.id,
                type="note",
                title=n.title,
                updated_at=n.created_at.isoformat() if n.created_at else "",
                subject_id=n.resource.subject_id if n.resource else None,
                subject_name=subjects.get(n.resource.subject_id) if n.resource else None,
            )
        )

    items.sort(key=lambda x: x.updated_at, reverse=True)
    return items[:20]
