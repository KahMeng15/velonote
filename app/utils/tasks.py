"""Background task management"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from app.config import get_settings
from app.models.db import Task
from app.utils.db import SessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()


def _serialize_result(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value)
    except TypeError:
        return json.dumps({"value": str(value)})


def _deserialize_result(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


class TaskManager:
    """Manage background tasks and processing"""

    @staticmethod
    def submit_task(task_id: str, task_type: str, user_id: int, **kwargs) -> str:
        """
        Submit a background task for processing (stored in DB for worker to pick up)
        """
        try:
            logger.info(f"Submitting task {task_id} of type {task_type}")

            db = SessionLocal()
            try:
                task = db.query(Task).filter(Task.task_id == task_id).first()
                if not task:
                    task = Task(
                        task_id=task_id,
                        user_id=user_id,
                        task_type=task_type,
                        status="pending",
                        progress=0,
                        input_data=_serialize_result(
                            {"kwargs": {**kwargs, "user_id": user_id, "task_id": task_id}}
                        ),
                    )
                    db.add(task)
                else:
                    task.user_id = user_id
                    task.task_type = task_type
                    task.status = "pending"
                    task.progress = 0
                    task.input_data = _serialize_result(
                        {"kwargs": {**kwargs, "user_id": user_id, "task_id": task_id}}
                    )
                    task.result = None
                    task.error_message = None
                    task.updated_at = datetime.utcnow()
                db.commit()
            finally:
                db.close()

            return task_id
        except Exception as e:
            logger.error(f"Error submitting task {task_id}: {e}")
            raise

    @staticmethod
    def _update_db_task(
        task_id: str,
        status: str | None = None,
        result: Any = None,
        error: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        intermediate_result: Any | None = None,
    ) -> None:
        db = SessionLocal()
        try:
            db_task = db.query(Task).filter(Task.task_id == task_id).first()
            if not db_task:
                return

            if status is not None:
                db_task.status = status
            if result is not None:
                db_task.result = _serialize_result(result)
            if error is not None:
                db_task.error_message = error
            if progress is not None:
                db_task.progress = min(100, max(0, progress))
            if message is not None:
                db_task.message = message
            db_task.updated_at = datetime.utcnow()
            db.commit()

            # Publish WebSocket update
            from app.utils.websocket import manager

            task_type = db_task.task_type or ""
            input_kwargs = {}
            if isinstance(db_task.input_data, dict):
                input_kwargs = db_task.input_data.get("kwargs", {})

            payload = {
                "task_id": task_id,
                "task_type": task_type,
                "status": db_task.status,
                "result": result if status == "completed" else None,
                "error": error if status == "failed" else None,
                "progress": db_task.progress or 0,
                "message": message,
                "intermediate_result": intermediate_result,
                "resource_id": input_kwargs.get("resource_id"),
                "exercise_id": input_kwargs.get("exercise_id"),
                "note_id": input_kwargs.get("note_id"),
            }
            manager.publish_update(db_task.user_id, payload)

        except Exception as exc:
            logger.error(f"Failed to update DB task {task_id}: {exc}")
        finally:
            db.close()

    @staticmethod
    def get_task_status(task_id: str, user_id: int | None = None) -> dict | None:
        """Get status of a task"""
        db = SessionLocal()
        try:
            query = db.query(Task).filter(Task.task_id == task_id)
            if user_id is not None:
                query = query.filter(Task.user_id == user_id)
            db_task = query.first()

            if db_task:
                return {
                    "task_id": db_task.task_id,
                    "status": db_task.status,
                    "progress": db_task.progress or 0,
                    "created_at": db_task.created_at.isoformat() if db_task.created_at else None,
                    "updated_at": db_task.updated_at.isoformat() if db_task.updated_at else None,
                    "result": _deserialize_result(db_task.result),
                    "error": db_task.error_message,
                    "message": db_task.message,
                    "task_type": db_task.task_type,
                }
        except Exception as exc:
            logger.error(f"Failed to load task {task_id} from DB: {exc}")
        finally:
            db.close()

        return None

    @staticmethod
    def update_task_progress(
        task_id: str,
        progress: int,
        message: str | None = None,
        intermediate_result: Any | None = None,
    ):
        """Update task progress (0-100) with optional status message and partial results"""
        bounded = min(100, max(0, progress))
        TaskManager._update_db_task(
            task_id, progress=bounded, message=message, intermediate_result=intermediate_result
        )

    @staticmethod
    def get_active_tasks(user_id: int) -> list:
        """Get all pending/processing tasks for a user, including recently finished ones"""
        db = SessionLocal()
        try:
            # Include tasks that are pending, processing, or running
            # Also include tasks that finished in the last 5 minutes so they show up in the UI
            five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
            tasks = (
                db.query(Task)
                .filter(
                    Task.user_id == user_id,
                    Task.task_type != "chat_response",
                    (
                        (Task.status.in_(["pending", "processing", "running"]))
                        | (Task.updated_at >= five_minutes_ago)
                    ),
                )
                .order_by(Task.created_at.asc())
                .all()
            )

            return [
                {
                    "task_id": t.task_id,
                    "task_type": t.task_type,
                    "status": t.status,
                    "progress": t.progress or 0,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                    "input_data": _deserialize_result(t.input_data),
                    "error": t.error_message,
                    "message": t.message,
                }
                for t in tasks
            ]
        except Exception as exc:
            logger.error(f"Failed to load active tasks for user {user_id}: {exc}")
            return []
        finally:
            db.close()

    @staticmethod
    def cancel_task(task_id: str, user_id: int) -> bool:
        """Cancel a pending/processing task"""
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.task_id == task_id, Task.user_id == user_id).first()
            if not task:
                return False

            if task.status in ["completed", "failed", "cancelled"]:
                return False

            task.status = "failed"
            task.error_message = "Cancelled by user"
            task.updated_at = datetime.utcnow()
            db.commit()

            # Notify UI
            from app.utils.websocket import manager

            manager.publish_update(
                user_id,
                {
                    "task_id": task_id,
                    "status": "failed",
                    "error": "Cancelled by user",
                    "progress": task.progress,
                },
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to cancel task {task_id}: {exc}")
            return False
        finally:
            db.close()

    @staticmethod
    def cleanup_old_tasks(retention_days: int | None = None) -> int:
        """Delete completed/failed tasks older than retention period."""
        days = retention_days if retention_days is not None else settings.TASK_RETENTION_DAYS
        if days <= 0:
            return 0

        cutoff = datetime.utcnow() - timedelta(days=days)
        db = SessionLocal()
        try:
            old_tasks = db.query(Task).filter(
                Task.updated_at < cutoff, Task.status.in_(["completed", "failed"])
            )
            deleted_count = old_tasks.count()
            old_tasks.delete(synchronize_session=False)
            db.commit()
            return deleted_count
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed task cleanup: {exc}")
            return 0
        finally:
            db.close()


class NoteTask:
    """Note generation task"""

    @staticmethod
    async def generate(**kwargs) -> dict:
        import time

        from sqlalchemy import func

        from app.models.db import Exercise, Note, Resource, User
        from app.processing.ai_client import AIClient
        from app.utils.db import generate_random_id
        from app.utils.storage import StorageManager

        db = SessionLocal()
        try:
            user_id = kwargs.get("user_id")
            resource_id = kwargs.get("resource_id")
            mode = kwargs.get("mode", "elaborate")
            output_format = kwargs.get("output_format", "sentence")
            processing_method = kwargs.get("processing_method", "whole")
            split_level = kwargs.get("split_level", "h2")
            custom_prompt = kwargs.get("custom_prompt", None)
            prompt_name = kwargs.get("prompt_name", None)
            prompt_icon = kwargs.get("prompt_icon", None)

            user = db.query(User).filter(User.id == user_id).first()

            title = kwargs.get("title")
            resource_ids = kwargs.get("resource_ids")
            exercise_ids = kwargs.get("exercise_ids")

            content_parts = []

            # Gather resource content
            if resource_ids:
                for rid in resource_ids:
                    r = db.query(Resource).filter(Resource.id == rid).first()
                    r_text = StorageManager.get_resource_text(rid) or ""
                    if r_text:
                        content_parts.append(f"--- Document: {r.title} ---\n{r_text}")

            # Gather exercise content
            if exercise_ids:
                for eid in exercise_ids:
                    ex = db.query(Exercise).filter(Exercise.id == eid).first()
                    if not ex:
                        continue
                    ex_questions = StorageManager.get_exercise_json(eid) or []
                    if isinstance(ex_questions, list) and len(ex_questions) > 0:
                        ex_parts = [f"--- Exercise: {ex.title} ---"]
                        for i, q in enumerate(ex_questions, 1):
                            q_text = q.get("question_text", "") or ""
                            a_text = q.get("answer_text", "") or ""
                            explanation = q.get("explanation", "") or ""
                            ref_quote = q.get("reference_quote", "") or ""
                            q.get("reference_resource_id") or ""

                            ex_parts.append(f"Question {i}: {q_text}")
                            if a_text:
                                ex_parts.append(f"Answer: {a_text}")
                            if explanation:
                                ex_parts.append(f"Explanation: {explanation}")
                            if ref_quote:
                                ex_parts.append(f"Reference Quote: {ref_quote}")
                        content_parts.append("\n\n".join(ex_parts))

                if not title:
                    exercises = db.query(Exercise).filter(Exercise.id.in_(exercise_ids)).all()
                    ex_dict = {e.id: e for e in exercises}
                    exercises_ordered = [ex_dict[eid] for eid in exercise_ids if eid in ex_dict]
                    title = "Exercise Notes: " + ", ".join([e.title for e in exercises_ordered[:3]])
                    if len(exercises_ordered) > 3:
                        title += "..."

            # If still no resources or exercises, fall back to single resource
            if not content_parts and resource_id:
                resource = db.query(Resource).filter(Resource.id == resource_id).first()
                r_text = StorageManager.get_resource_text(resource_id) or ""
                if r_text:
                    content_parts.append(f"--- Document: {resource.title} ---\n{r_text}")
                if not title and resource:
                    title = resource.title

            resource_content = "\n\n".join(content_parts) if content_parts else ""

            ai_client = AIClient(user, db=db, category="processing")

            start_time = time.time()
            task_id = kwargs.get("task_id")

            def progress_callback(percent, message=None, intermediate_result=None):
                if task_id:
                    msg = message
                    if not msg:
                        msg = "Generating note..."
                        if percent > 20:
                            msg = "Analyzing content..."
                        if percent > 50:
                            msg = "Drafting sections..."
                        if percent > 80:
                            msg = "Finalizing note..."
                    TaskManager.update_task_progress(
                        task_id, percent, message=msg, intermediate_result=intermediate_result
                    )

            note_content = await ai_client.generate_summary(
                content=resource_content,
                mode=mode,
                output_format=output_format,
                processing_method=processing_method,
                split_level=split_level,
                custom_prompt=custom_prompt,
                progress_callback=progress_callback,
            )

            processing_time = time.time() - start_time

            doc_id = kwargs.get("note_id")
            doc = None
            if doc_id:
                doc = db.query(Note).filter(Note.id == doc_id).first()

            import json

            e_ids = kwargs.get("exercise_ids")

            if doc:
                doc.title = title
                doc.file_path = f"note_{resource_id or 'ex'}_{doc.version}.md"
                doc.processing_time = processing_time
                doc.processing_time_ms = int(processing_time * 1000)
                doc.model = (
                    f"{ai_client.provider.capitalize()} ({ai_client.ai_model_name})"
                    if ai_client.ai_model_name
                    else ai_client.provider.capitalize()
                )
                if e_ids:
                    doc.exercise_ids = json.dumps(e_ids)
            else:
                if not doc_id:
                    doc_id = generate_random_id(db, Note)
                max_version = (
                    db.query(func.max(Note.version))
                    .filter(Note.resource_id == resource_id)
                    .scalar()
                    or 0
                    if resource_id
                    else 0
                )
                next_version = max_version + 1
                r_ids = kwargs.get("resource_ids")

                doc = Note(
                    id=doc_id,
                    version=next_version,
                    resource_id=resource_id,
                    user_id=user_id,
                    title=title,
                    summary_type="summary",
                    file_path=f"note_{resource_id or 'ex'}_{next_version}.md",
                    mode=mode,
                    output_format=output_format,
                    processing_method=processing_method,
                    split_level=split_level,
                    custom_prompt=custom_prompt,
                    prompt_name=prompt_name,
                    prompt_icon=prompt_icon,
                    processing_time=processing_time,
                    processing_time_ms=int(processing_time * 1000),
                    model=f"{ai_client.provider.capitalize()} ({ai_client.ai_model_name})"
                    if ai_client.ai_model_name
                    else ai_client.provider.capitalize(),
                    resource_ids=json.dumps(r_ids) if r_ids and len(r_ids) > 1 else None,
                    exercise_ids=json.dumps(e_ids) if e_ids else None,
                )
                db.add(doc)
            db.commit()

            StorageManager.save_note_text(doc_id, note_content)

            if task_id:
                TaskManager.update_task_progress(task_id, 100)

            return {
                "id": doc_id,
                "resource_id": resource_id,
                "title": doc.title,
                "content": note_content,
                "mode": mode,
                "output_format": output_format,
                "processing_method": processing_method,
                "split_level": split_level,
                "processing_time": processing_time,
                "processing_time_ms": int(processing_time * 1000),
                "model": doc.model,
                "version": doc.version,
                "is_user_edited": False,
                "status": "completed",
            }
        finally:
            db.close()


class ChatTask:
    """Chat response task"""

    @staticmethod
    async def respond(**kwargs) -> dict:
        # This will be more complex as it needs to duplicate most of chat.py logic
        # For now, let's keep it minimal or plan to refactor chat.py to be more modular
        from app.routers.chat import ask_question_logic

        return await ask_question_logic(**kwargs)


class OCRTask:
    """OCR processing task"""

    @staticmethod
    def process_file(file_path: str, **kwargs) -> dict:
        from app.processing.ocr import OCRProcessor

        try:
            logger.info(f"Processing file for OCR: {file_path}")
            if file_path.endswith(".pdf"):
                file_type = "application/pdf"
            elif file_path.endswith(".pptx"):
                file_type = (
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                )
            elif file_path.endswith(".ppt"):
                file_type = "application/vnd.ms-powerpoint"
            elif file_path.lower().endswith((".png", ".jpg", ".jpeg")):
                file_type = "image/jpeg"
            else:
                raise ValueError(f"Unsupported file type: {file_path}")
            extracted_text = OCRProcessor.extract_text(file_path, file_type)
            chunks = OCRProcessor.chunk_text(extracted_text)
            return {"extracted_text": extracted_text, "chunks": chunks, "chunk_count": len(chunks)}
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            raise


class EmbeddingsTask:
    """Embeddings generation task"""

    @staticmethod
    def generate_embeddings(text_chunks: list, **kwargs) -> dict:
        from app.processing.search import EmbeddingsManager

        try:
            logger.info(f"Generating embeddings for {len(text_chunks)} chunks")
            embeddings_mgr = EmbeddingsManager()
            embeddings = embeddings_mgr.embed_texts(text_chunks)
            return {
                "embeddings": embeddings.tolist(),
                "chunks": text_chunks,
                "embedding_count": len(embeddings),
            }
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise
