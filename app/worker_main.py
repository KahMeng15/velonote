import asyncio
import json
import logging
import traceback
from datetime import datetime

from sqlalchemy import func

from app.logging_config import setup_logging
from app.models.db import RateLimitConfig, Task
from app.utils.db import SessionLocal
from app.utils.tasks import ChatTask, EmbeddingsTask, NoteTask, OCRTask, TaskManager
from app.logging_config import setup_logging, current_entity_id, current_user_id
setup_logging()
logger = logging.getLogger(__name__)

from app.processing.exercise_processor import generate_exercise_task, process_exercise_task
from app.processing.note_processor import process_resource_task

# Registry of supported tasks (can be sync or async)
TASK_REGISTRY = {
    "ocr": OCRTask.process_file,
    "embedding": EmbeddingsTask.generate_embeddings,
    "resource_processing": process_resource_task,
    "note_generation": NoteTask.generate,
    "chat_response": ChatTask.respond,
    "exercise_extraction": process_exercise_task,
    "exercise_generation": generate_exercise_task,
}


async def process_next_task():
    db = SessionLocal()
    try:
        # Load per-user concurrency limit
        rate_limits = db.query(RateLimitConfig).first()
        max_concurrent = rate_limits.concurrent_tasks_per_user if rate_limits else 1

        # Base query for pending tasks
        pending_query = db.query(Task).filter(Task.status == "pending")

        # Apply per-user concurrency limit if not unlimited (unlimited = 0 or -1)
        if max_concurrent > 0:
            # Find users who have already reached their concurrent task limit
            # These are users with >= max_concurrent tasks in 'running' status
            running_users_subquery = (
                db.query(Task.user_id)
                .filter(Task.status == "running")
                .group_by(Task.user_id)
                .having(func.count(Task.id) >= max_concurrent)
                .subquery()
            )

            pending_query = pending_query.filter(
                ~Task.user_id.in_(db.query(running_users_subquery.c.user_id))
            )

        # Find the oldest eligible pending task
        task = pending_query.order_by(Task.created_at.asc()).first()

        if not task:
            return False

        # Mark as running
        task.status = "running"
        task.updated_at = datetime.utcnow()
        db.commit()

        task_id = task.task_id
        task_type = task.task_type
        input_data = task.input_data

        logger.info(f"Picked up task {task_id} of type {task_type}")

        # Parse kwargs
        kwargs = {}
        if input_data:
            try:
                parsed = json.loads(input_data)
                kwargs = parsed.get("kwargs", {})
            except Exception as e:
                logger.error(f"Failed to parse input data for task {task_id}: {e}")

        # Execute
        handler = TASK_REGISTRY.get(task_type)
        if not handler:
            raise ValueError(f"Unknown task type: {task_type}")

        TaskManager.update_task_progress(task_id, 10)

        # Extract entity ID for logging
        entity_id = kwargs.get("resource_id") or kwargs.get("exercise_id") or kwargs.get("note_id")
        
        # Set context vars for process logging
        token_entity = current_entity_id.set(entity_id)
        token_user = current_user_id.set(task.user_id)

        try:
            # Execute task (handle both sync and async)
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**kwargs)
            else:
                result = handler(**kwargs)
        finally:
            # Reset context vars
            current_entity_id.reset(token_entity)
            current_user_id.reset(token_user)

        # Mark complete or failed based on result
        if isinstance(result, dict) and result.get("status") in ("error", "failed"):
            TaskManager._update_db_task(task_id, status="failed", result=result, progress=0)
            logger.info(f"Task {task_id} failed with error: {result}")
        elif isinstance(result, dict) and result.get("status") == "cancelled":
            TaskManager._update_db_task(task_id, status="cancelled", result=result)
            logger.info(f"Task {task_id} cancelled")
        else:
            TaskManager._update_db_task(task_id, status="completed", result=result, progress=100)
            logger.info(f"Task {task_id} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Task processing failed: {e}")
        logger.error(traceback.format_exc())
        if "task_id" in locals():
            TaskManager._update_db_task(task_id, status="failed", error=str(e), progress=0)
        db.rollback()
        return False
    finally:
        db.close()


async def run_periodic_backup_loop():
    """Periodically execute database backup every 24 hours."""
    from app.utils.backup import perform_db_backup

    # Wait 30 seconds after worker startup to let services stabilize
    await asyncio.sleep(30)
    while True:
        try:
            logger.info("Executing scheduled database backup...")
            await asyncio.to_thread(perform_db_backup)
        except Exception as e:
            logger.error(f"Error during scheduled database backup: {e}")
        # Sleep for 24 hours (86400s)
        await asyncio.sleep(86400)


async def main():
    logger.info("Starting background worker (async mode)...")
    backup_task = asyncio.create_task(run_periodic_backup_loop())
    try:
        while True:
            try:
                processed = await process_next_task()
                if not processed:
                    await asyncio.sleep(0.5)  # Wait before polling again
            except KeyboardInterrupt:
                logger.info("Worker shutting down...")
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(5)
    finally:
        backup_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
