import logging
import contextvars

current_entity_id = contextvars.ContextVar("current_entity_id", default=None)
current_user_id = contextvars.ContextVar("current_user_id", default=None)

class EntityLogHandler(logging.Handler):
    def emit(self, record):
        entity_id = current_entity_id.get()
        if not entity_id:
            return
            
        log_entry = self.format(record)
        # 1. Write to file
        from app.utils.storage import StorageManager
        StorageManager.append_process_log(entity_id, log_entry)
        
        # 2. Broadcast via websocket
        user_id = current_user_id.get()
        if user_id:
            from app.utils.websocket import manager
            manager.publish_update(user_id, {
                "type": "process_log",
                "entity_id": entity_id,
                "log": log_entry
            })
