"""WebSocket router for real-time updates"""

import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.models.db import User
from app.utils.auth import decode_token
from app.utils.db import get_db
from app.utils.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/updates")
@router.websocket("/{token_param}")
async def websocket_endpoint(
    websocket: WebSocket, token_param: str | None = None, db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time task updates.
    Accepts immediately to avoid handshake rejections, then validates.
    """
    await websocket.accept()

    # Try to get token from various sources
    token = token_param
    if token == "updates":
        token = None

    if not token:
        token = websocket.cookies.get("access_token")
    if not token:
        token = websocket.query_params.get("token")

    if not token:
        logger.warning("WebSocket auth failed: No token found")
        await websocket.send_json({"error": "Unauthorized", "message": "No token found"})
        await websocket.close(code=1008)
        return

    payload = decode_token(token)
    if not payload:
        logger.warning("WebSocket auth failed: Invalid token")
        await websocket.send_json({"error": "Unauthorized", "message": "Invalid token"})
        await websocket.close(code=1008)
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=1008)
        return

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        await websocket.close(code=1008)
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            # Keep connection alive and wait for client messages (if any)
            await websocket.receive_text()
            # We don't expect client messages for now, but we keep it to handle disconnects
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error for user {user.id}: {e}")
        manager.disconnect(user.id, websocket)
