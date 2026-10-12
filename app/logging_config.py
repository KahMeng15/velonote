import logging.config
import os
import contextvars
from logging import Handler

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

current_entity_id = contextvars.ContextVar("current_entity_id", default=None)
current_user_id = contextvars.ContextVar("current_user_id", default=None)

class EntityLogHandler(Handler):
    def emit(self, record):
        entity_id = current_entity_id.get()
        if not entity_id:
            return
            
        is_stream = getattr(record, "stream_token", False)
        log_entry = record.getMessage() if is_stream else self.format(record)
        
        # 1. Write to file
        from app.utils.storage import StorageManager
        StorageManager.append_process_log(entity_id, log_entry, newline=not is_stream)
        
        # 2. Broadcast via websocket
        user_id = current_user_id.get()
        if user_id:
            from app.utils.websocket import manager
            try:
                # We need to run this async if we are in an async context, but publish_update is synchronous!
                manager.publish_update(user_id, {
                    "type": "process_log_stream" if is_stream else "process_log",
                    "entity_id": entity_id,
                    "log": log_entry
                })
            except Exception:
                pass

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
        },
        "process_logger": {
            "class": "app.logging_config.EntityLogHandler",
            "formatter": "standard",
            "level": "INFO",
        },
        "backend_file": {
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "backend.log"),
            "formatter": "standard",
            "level": "INFO",
        },
        "worker_file": {
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "worker.log"),
            "formatter": "standard",
            "level": "INFO",
        },
        "processing_file": {
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "processing.log"),
            "formatter": "standard",
            "level": "INFO",
        },
        "error_file": {
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "errors.log"),
            "formatter": "standard",
            "level": "ERROR",
        },
    },
    "loggers": {
        "app": {
            "handlers": ["console", "backend_file", "process_logger", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "app.processing": {
            "handlers": ["console", "processing_file", "process_logger", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "app.worker_main": {
            "handlers": ["console", "worker_file", "process_logger", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "__main__": {
            "handlers": ["console", "worker_file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "fastapi": {
            "handlers": ["console", "backend_file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn": {
            "handlers": ["console", "backend_file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console", "backend_file", "error_file"],
        "level": "INFO",
    },
}


def setup_logging():
    logging.config.dictConfig(LOGGING_CONFIG)
