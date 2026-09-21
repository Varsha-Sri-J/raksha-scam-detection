import asyncio
import logging
from typing import Dict, List, Set
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
            results = await asyncio.gather(
                *[ws.send_text(payload) for ws in sockets], return_exceptions=True
            )
            # Detect failed / dead sockets
            dead_sockets = [
                ws for ws, res in zip(sockets, results) if isinstance(res, Exception)
            ]
            if dead_sockets:
                async with self._lock:
                    if session_id in self.active_connections:
                        for ws in dead_sockets:
                            self.active_connections[session_id].discard(ws)
                        if not self.active_connections[session_id]:
                            del self.active_connections[session_id]
                logger.warning(
                    "Pruned %d dead sockets for session %s", len(dead_sockets), session_id
                )

    async def get_connection_count(self, session_id: str) -> int:
        """Return the number of active WebSocket connections for a session."""
        async with self._lock:
            return len(self.active_connections.get(session_id, set()))

    async def get_active_sessions(self) -> List[str]:
        """Return a list of all session IDs with at least one active connection."""
        async with self._lock:
            return list(self.active_connections.keys())


# Global singleton instance
manager = ConnectionManager()
