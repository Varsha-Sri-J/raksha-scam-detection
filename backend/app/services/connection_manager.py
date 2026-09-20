import asyncio
import logging
from typing import Dict, Set
from fastapi import WebSocket
from backend.app.models import WSMessage

logger = logging.getLogger("raksha.backend.connection_manager")


class ConnectionManager:
    """Thread-safe WebSocket connection manager for call sessions."""

    def __init__(self) -> None:
        # Maps session_id to set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Global dashboard listeners
        self.dashboard_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect_session(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if session_id not in self.active_connections:
                self.active_connections[session_id] = set()
            self.active_connections[session_id].add(websocket)
        logger.info("Client connected to session %s", session_id)

    async def disconnect_session(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if session_id in self.active_connections:
                self.active_connections[session_id].discard(websocket)
                if not self.active_connections[session_id]:
                    del self.active_connections[session_id]
        logger.info("Client disconnected from session %s", session_id)

    async def broadcast_session(self, session_id: str, message: WSMessage) -> None:
        async with self._lock:
            sockets = list(self.active_connections.get(session_id, set()))
        if sockets:
            payload = message.model_dump_json()
            await asyncio.gather(
                *[ws.send_text(payload) for ws in sockets], return_exceptions=True
            )


# Global singleton instance
manager = ConnectionManager()
