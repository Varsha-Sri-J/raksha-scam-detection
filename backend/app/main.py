import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.models import (
    CallSession,
    RiskAssessment,
    SessionStatus,
    SpeakerType,
    TranscriptSegment,
    WSMessage,
    WSMessageType,
)
from backend.app.risk_engine import risk_engine
from backend.app.services.session_store import session_store

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("raksha.backend")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Real-Time Scam and Manipulation Detection Engine - Phase 1 Foundation",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Connection Manager for WebSockets
class ConnectionManager:
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


manager = ConnectionManager()


# Request / Response Schemas
class CreateSessionRequest(BaseModel):
    caller_id: Optional[str] = "Unknown"
    callee_id: Optional[str] = "Protected Callee"
    session_id: Optional[str] = None


class AddSegmentRequest(BaseModel):
    speaker: SpeakerType = SpeakerType.UNKNOWN
    text: str
    is_final: bool = True


# --- REST Endpoints ---


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for Raksha service."""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": time.time(),
    }


@app.post("/api/sessions", response_model=CallSession, status_code=status.HTTP_201_CREATED, tags=["Sessions"])
async def create_session(payload: CreateSessionRequest) -> CallSession:
    """Initialize a new call session."""
    session = await session_store.create_session(
        session_id=payload.session_id,
        caller_id=payload.caller_id,
        callee_id=payload.callee_id,
    )
    # Initialize baseline risk assessment
    baseline_risk = risk_engine.evaluate_session(session)
    await session_store.update_risk_assessment(session.session_id, baseline_risk)
    session.latest_risk = baseline_risk
    return session


@app.get("/api/sessions", response_model=List[CallSession], tags=["Sessions"])
async def list_sessions(status_filter: Optional[SessionStatus] = None) -> List[CallSession]:
    """List all call sessions."""
    return await session_store.list_sessions(status=status_filter)


@app.get("/api/sessions/{session_id}", response_model=CallSession, tags=["Sessions"])
async def get_session(session_id: str) -> CallSession:
    """Retrieve session details by ID."""
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


@app.post("/api/sessions/{session_id}/segments", response_model=TranscriptSegment, tags=["Sessions"])
async def add_segment(session_id: str, payload: AddSegmentRequest) -> TranscriptSegment:
    """Add a transcript segment and trigger baseline risk evaluation."""
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    segment = TranscriptSegment(
        session_id=session_id,
        speaker=payload.speaker,
        text=payload.text,
        is_final=payload.is_final,
    )
    await session_store.add_transcript_segment(session_id, segment)

    # Evaluate risk
    risk = risk_engine.evaluate_session(session)
    await session_store.update_risk_assessment(session_id, risk)

    # Broadcast via WebSocket
    await manager.broadcast_session(
        session_id,
        WSMessage(
            type=WSMessageType.TRANSCRIPT_STREAM,
            data={"segment": segment.model_dump()},
        ),
    )
    await manager.broadcast_session(
        session_id,
        WSMessage(
            type=WSMessageType.RISK_UPDATE,
            data={"risk": risk.model_dump()},
        ),
    )

    return segment


@app.post("/api/sessions/{session_id}/end", response_model=CallSession, tags=["Sessions"])
async def end_session(session_id: str) -> CallSession:
    """Mark an active call session as ended."""
    session = await session_store.end_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    await manager.broadcast_session(
        session_id,
        WSMessage(
            type=WSMessageType.SESSION_STATUS,
            data={"status": session.status.value},
        ),
    )
    return session


# --- WebSocket Endpoint ---


@app.websocket("/ws/call/{session_id}")
async def websocket_call_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Real-time WebSocket endpoint for call sessions."""
    await manager.connect_session(session_id, websocket)

    # Ensure session exists or auto-create for quick connection
    session = await session_store.get_session(session_id)
    if not session:
        session = await session_store.create_session(session_id=session_id)
        baseline_risk = risk_engine.evaluate_session(session)
        await session_store.update_risk_assessment(session_id, baseline_risk)
        session.latest_risk = baseline_risk

    # Send initial session state to client upon connection
    await websocket.send_text(
        WSMessage(
            type=WSMessageType.SESSION_STATUS,
            data={"session": session.model_dump()},
        ).model_dump_json()
    )

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                msg_dict = json.loads(raw_data)
                msg_type = msg_dict.get("type")

                if msg_type == WSMessageType.PING.value:
                    await websocket.send_text(
                        WSMessage(type=WSMessageType.PONG, data={"reply": "pong"}).model_dump_json()
                    )

                elif msg_type == WSMessageType.TRANSCRIPT_STREAM.value:
                    payload = msg_dict.get("data", {})
                    segment = TranscriptSegment(
                        session_id=session_id,
                        speaker=SpeakerType(payload.get("speaker", SpeakerType.UNKNOWN.value)),
                        text=payload.get("text", ""),
                        is_final=payload.get("is_final", True),
                    )
                    await session_store.add_transcript_segment(session_id, segment)

                    risk = risk_engine.evaluate_session(session)
                    await session_store.update_risk_assessment(session_id, risk)

                    # Broadcast to all listeners on this session
                    await manager.broadcast_session(
                        session_id,
                        WSMessage(
                            type=WSMessageType.TRANSCRIPT_STREAM,
                            data={"segment": segment.model_dump()},
                        ),
                    )
                    await manager.broadcast_session(
                        session_id,
                        WSMessage(
                            type=WSMessageType.RISK_UPDATE,
                            data={"risk": risk.model_dump()},
                        ),
                    )

            except json.JSONDecodeError:
                await websocket.send_text(
                    WSMessage(
                        type=WSMessageType.ERROR,
                        data={"error": "Invalid JSON format"},
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        await manager.disconnect_session(session_id, websocket)
    except Exception as exc:
        logger.exception("Unexpected error in websocket loop: %s", exc)
        await manager.disconnect_session(session_id, websocket)
