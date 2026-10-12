from fastapi import APIRouter, Depends, HTTPException
from app.models.db import User
from app.utils.auth import get_current_user
from app.utils.storage import StorageManager

router = APIRouter(prefix="/logs", tags=["logs"])

@router.get("/{entity_id}")
def get_entity_process_logs(
    entity_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the full process log for a specific resource, exercise, or note."""
    # Ensure they have access to it
    from app.utils.storage import _get_user_id_for_entity
    owner_id = _get_user_id_for_entity(entity_id)
    if str(owner_id) != str(current_user.id) and str(owner_id) != "unowned":
        raise HTTPException(status_code=403, detail="Not authorized to view logs for this entity")
        
    logs = StorageManager.get_process_log(entity_id)
    return {"entity_id": entity_id, "logs": logs}
