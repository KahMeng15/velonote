import functools
import json
import logging
import os
from typing import Any

from app.utils.cache import delete_cache_sync, get_cache_sync, set_cache_sync
from app.utils.db import SessionLocal
from app.utils.paths import (
    LEGACY_EXTRACTED_IMAGES_DIR,
    LEGACY_GENERATED_DIR,
    LEGACY_OUTPUT_DIR,
    USERS_DIR,
)

logger = logging.getLogger(__name__)


# Helper to find user ID for an entity
@functools.lru_cache(maxsize=10000)
def _get_user_id_for_entity(entity_id: str) -> str:
    """Find the user ID associated with a resource, note, or exercise."""
    # Prefix mapping
    if entity_id.startswith("rs_"):
        model_name = "Resource"
    elif entity_id.startswith("nt_"):
        model_name = "Note"
    elif entity_id.startswith("ex_"):
        model_name = "Exercise"
    else:
        return "unowned"

    try:
        from app.models.db import Exercise, Note, Resource
        model_class = {"Resource": Resource, "Note": Note, "Exercise": Exercise}[model_name]

        with SessionLocal() as db:
            entity = db.query(model_class).filter(model_class.id == entity_id).first()
            if entity:
                if model_name == "Note":
                    resource = db.query(Resource).filter(Resource.id == entity.resource_id).first()
                    if resource:
                        return str(resource.user_id)
                    # Note might also have a direct user_id fallback
                    if hasattr(entity, "user_id") and entity.user_id:
                        return str(entity.user_id)
                else:
                    # Resource and Exercise both have a direct user_id column
                    return str(entity.user_id)
    except Exception as e:
        logger.error(f"Error fetching user_id for {entity_id}: {e}")

    return "unowned"


def _ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


class StorageManager:
    """Central manager for file-based storage of large content with Redis caching.

    All paths are anchored to BASE_DIR (project root) for CWD-independent operation.
    """

    # ================================================================
    # User-scoped directory helpers (caller provides user_id directly)
    # ================================================================

    @staticmethod
    def get_user_data_dir(user_id: int | str) -> str:
        return os.path.join(USERS_DIR, str(user_id))

    @staticmethod
    def get_upload_dir(user_id: int | str) -> str:
        path = os.path.join(USERS_DIR, str(user_id), "uploads")
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def get_upload_path(user_id: int | str, filename: str) -> str:
        return os.path.join(StorageManager.get_upload_dir(user_id), filename)

    @staticmethod
    def get_resources_dir(user_id: int | str) -> str:
        path = os.path.join(USERS_DIR, str(user_id), "resources")
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def get_extracted_images_dir(user_id: int | str, resource_id: str) -> str:
        path = os.path.join(USERS_DIR, str(user_id), "extracted_images", resource_id)
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def get_exports_dir(user_id: int | str, resource_id: str) -> str:
        path = os.path.join(USERS_DIR, str(user_id), "exports", resource_id)
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def get_user_images_dir(user_id: int | str, resource_id: str) -> str:
        path = os.path.join(USERS_DIR, str(user_id), "user_images", resource_id)
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def get_notes_dir(user_id: int | str) -> str:
        path = os.path.join(USERS_DIR, str(user_id), "notes")
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def get_exercises_dir(user_id: int | str) -> str:
        path = os.path.join(USERS_DIR, str(user_id), "exercises")
        os.makedirs(path, exist_ok=True)
        return path

    # ================================================================
    # Entity-scoped directory helpers (resolve user_id from DB)
    # ================================================================

    @staticmethod
    def get_extracted_images_dir_for_resource(resource_id: str) -> str:
        """Resolve user_id and return extracted_images dir for a resource.
        Falls back to legacy path if resource is unowned."""
        user_id = _get_user_id_for_entity(resource_id)
        if user_id == "unowned":
            path = os.path.join(LEGACY_EXTRACTED_IMAGES_DIR, resource_id)
            os.makedirs(path, exist_ok=True)
            return path
        return StorageManager.get_extracted_images_dir(user_id, resource_id)

    @staticmethod
    def get_exports_dir_for_resource(resource_id: str) -> str:
        """Resolve user_id and return exports dir for a resource.
        Falls back to legacy generated dir if resource is unowned."""
        user_id = _get_user_id_for_entity(resource_id)
        if user_id == "unowned":
            path = os.path.join(LEGACY_GENERATED_DIR, resource_id)
            os.makedirs(path, exist_ok=True)
            return path
        return StorageManager.get_exports_dir(user_id, resource_id)

    # ================================================================
    # Legacy / flat-layout helpers
    # ================================================================

    @staticmethod
    def get_legacy_generated_dir() -> str:
        os.makedirs(LEGACY_GENERATED_DIR, exist_ok=True)
        return LEGACY_GENERATED_DIR

    @staticmethod
    def get_legacy_output_dir() -> str:
        os.makedirs(LEGACY_OUTPUT_DIR, exist_ok=True)
        return LEGACY_OUTPUT_DIR



    # ================================================================
    # Existing per-entity CRUD methods (unchanged)
    # ================================================================

    @staticmethod
    def _get_resource_path(resource_id: str, suffix: str = "", extension: str = "md") -> str:
        user_id = _get_user_id_for_entity(resource_id)
        filename = f"{resource_id}{suffix}.{extension}"
        return _ensure_dir(os.path.join(USERS_DIR, user_id, "resources", filename))

    @staticmethod
    def _get_resource_json_path(resource_id: str, suffix: str) -> str:
        """Return the path where save_resource_json would write, without creating the file."""
        return StorageManager._get_resource_path(resource_id, suffix=f"_{suffix}", extension="json")

    @staticmethod
    def _get_note_path(note_id: str, suffix: str = "", extension: str = "md") -> str:
        user_id = _get_user_id_for_entity(note_id)
        filename = f"{note_id}{suffix}.{extension}"
        return _ensure_dir(os.path.join(USERS_DIR, user_id, "notes", filename))

    @staticmethod
    def _get_exercise_path(exercise_id: str, suffix: str = "", extension: str = "json") -> str:
        user_id = _get_user_id_for_entity(exercise_id)
        filename = f"{exercise_id}{'_' + suffix if suffix else ''}.{extension}"
        return _ensure_dir(os.path.join(USERS_DIR, user_id, "exercises", filename))

    @staticmethod
    def _get_process_log_path(entity_id: str) -> str:
        user_id = _get_user_id_for_entity(entity_id)
        if entity_id.startswith("rs_"):
            return _ensure_dir(os.path.join(USERS_DIR, str(user_id), "resources", f"{entity_id}_process.log"))
        elif entity_id.startswith("ex_"):
            return _ensure_dir(os.path.join(USERS_DIR, str(user_id), "exercises", f"{entity_id}_process.log"))
        elif entity_id.startswith("nt_"):
            return _ensure_dir(os.path.join(USERS_DIR, str(user_id), "notes", f"{entity_id}_process.log"))
        else:
            return _ensure_dir(os.path.join(USERS_DIR, "unowned", "logs", f"{entity_id}_process.log"))
            
    @staticmethod
    def append_process_log(entity_id: str, log_entry: str, newline: bool = True):
        if not entity_id or not log_entry:
            return
        path = StorageManager._get_process_log_path(entity_id)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(log_entry + ("\n" if newline else ""))
        except Exception as e:
            logger.error(f"Failed to write process log for {entity_id}: {e}")

    @staticmethod
    def get_process_log(entity_id: str) -> str:
        path = StorageManager._get_process_log_path(entity_id)
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    # --- Resource Content Methods ---

    @staticmethod
    def save_resource_text(resource_id: str, text: str):
        if not text:
            return
        path = StorageManager._get_resource_path(resource_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            logger.debug(f"Saved resource text to {path}")

            cache_key = f"resource_text:{resource_id}"
            set_cache_sync(cache_key, text)
        except Exception as e:
            logger.error(f"Failed to save resource text for {resource_id}: {e}")

    @staticmethod
    def get_resource_text(resource_id: str) -> str | None:
        cache_key = f"resource_text:{resource_id}"
        cached = get_cache_sync(cache_key)
        if cached:
            logger.info(f"Cache hit for resource text: {resource_id}")
            return cached

        path = StorageManager._get_resource_path(resource_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
                set_cache_sync(cache_key, content)
                return content
        except Exception as e:
            logger.error(f"Failed to read resource text for {resource_id}: {e}")
            return None

    @staticmethod
    def save_resource_json(resource_id: str, suffix: str, data: dict | Any):
        if data is None:
            return
        path = StorageManager._get_resource_path(resource_id, suffix=f"_{suffix}", extension="json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.debug(f"Saved resource {suffix} to {path}")

            cache_key = f"resource_json:{resource_id}:{suffix}"
            set_cache_sync(cache_key, data)
        except Exception as e:
            logger.error(f"Failed to save resource {suffix} for {resource_id}: {e}")

    @staticmethod
    def get_resource_json(resource_id: str, suffix: str) -> dict | Any | None:
        cache_key = f"resource_json:{resource_id}:{suffix}"
        cached = get_cache_sync(cache_key)
        if cached:
            logger.info(f"Cache hit for resource json: {resource_id}:{suffix}")
            return cached

        path = StorageManager._get_resource_path(resource_id, suffix=f"_{suffix}", extension="json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                set_cache_sync(cache_key, data)
                return data
        except Exception as e:
            logger.error(f"Failed to read resource {suffix} for {resource_id}: {e}")
            return None

    # --- Note Methods ---

    @staticmethod
    def save_note_text(note_id: str, text: str, is_quickread: bool = False):
        if text is None:
            return
        suffix = "_quickread" if is_quickread else ""
        path = StorageManager._get_note_path(note_id, suffix=suffix)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            logger.debug(f"Saved note {note_id}{suffix} to {path}")

            cache_key = f"note_text:{note_id}{suffix}"
            set_cache_sync(cache_key, text)
        except Exception as e:
            logger.error(f"Failed to save note {note_id}: {e}")

    @staticmethod
    def get_note_text(note_id: str, is_quickread: bool = False) -> str | None:
        suffix = "_quickread" if is_quickread else ""
        cache_key = f"note_text:{note_id}{suffix}"
        cached = get_cache_sync(cache_key)
        if cached:
            logger.info(f"Cache hit for note text: {note_id}{suffix}")
            return cached

        path = StorageManager._get_note_path(note_id, suffix=suffix)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
                set_cache_sync(cache_key, content)
                return content
        except Exception as e:
            logger.error(f"Failed to read note {note_id}: {e}")
            return None

    # --- Deletion Methods ---

    @staticmethod
    def delete_resource_files(resource_id: str):
        patterns = [
            (StorageManager._get_resource_path(resource_id), f"resource_text:{resource_id}"),
            (
                StorageManager._get_resource_path(
                    resource_id, suffix="_structured", extension="json"
                ),
                f"resource_json:{resource_id}:structured",
            ),
            (
                StorageManager._get_resource_path(resource_id, suffix="_images", extension="json"),
                f"resource_json:{resource_id}:images",
            ),
        ]
        for path, cache_key in patterns:
            delete_cache_sync(cache_key)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"Deleted storage file: {path}")
                except Exception as e:
                    logger.error(f"Failed to delete {path}: {e}")

    @staticmethod
    def delete_note_files(note_id: str):
        patterns = [
            (StorageManager._get_note_path(note_id), f"note_text:{note_id}"),
            (
                StorageManager._get_note_path(note_id, suffix="_quickread"),
                f"note_text:{note_id}_quickread",
            ),
        ]
        for path, cache_key in patterns:
            delete_cache_sync(cache_key)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"Deleted storage file: {path}")
                except Exception as e:
                    logger.error(f"Failed to delete {path}: {e}")

    @staticmethod
    def save_exercise_json(exercise_id: str, data: dict | Any, suffix: str = ""):
        path = StorageManager._get_exercise_path(exercise_id, suffix=suffix, extension="json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write JSON for exercise {exercise_id}: {e}")
            raise e

    @staticmethod
    def get_exercise_json(exercise_id: str, suffix: str = "") -> dict | Any | None:
        path = StorageManager._get_exercise_path(exercise_id, suffix=suffix, extension="json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read JSON for exercise {exercise_id}: {e}")
            return None

    @staticmethod
    def delete_exercise_files(exercise_id: str):
        user_id = _get_user_id_for_entity(exercise_id)
        exercises_dir = os.path.join(USERS_DIR, user_id, "exercises")
        if not os.path.exists(exercises_dir):
            return
        for filename in os.listdir(exercises_dir):
            if filename.startswith(f"{exercise_id}"):
                file_path = os.path.join(exercises_dir, filename)
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted exercise file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")
