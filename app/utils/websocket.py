"""WebSocket connection manager for real-time client updates."""

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        """Register a new WebSocket connection."""
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info(
            f"User {user_id} connected. Active connections: {len(self.active_connections[user_id])}"
        )

    def disconnect(self, user_id: int, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected")

    async def broadcast_to_user(self, user_id: int, message: dict):
        """Send message to all local connections for a user."""
        if user_id not in self.active_connections:
            return

        disconnected = set()
        for connection in list(self.active_connections[user_id]):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.debug(f"Error sending message to user {user_id}: {e}")
                disconnected.add(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            self.active_connections[user_id].discard(connection)

    async def send_personal_message(self, websocket: WebSocket, message: dict):
        """Send message to specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    @staticmethod
    def publish_update(user_id: int, payload: dict):
        """
        Publish an update to active WebSocket connections.
        Safe for both sync and async callers without requiring Redis.
        """
        if user_id not in manager.active_connections:
            return

        try:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(manager.broadcast_to_user(user_id, payload))
            except RuntimeError:
                # No running event loop in current thread
                pass
        except Exception as e:
            logger.debug(f"Could not broadcast update to user {user_id}: {e}")


# Global connection manager
manager = ConnectionManager()
