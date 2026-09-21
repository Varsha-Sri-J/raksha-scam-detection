import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
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
from backend.app.services.connection_manager import manager
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.session_store import session_store

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("raksha.backend")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Real-Time Scam and Manipulation Detection Engine - Phase 3A Streaming Pipeline",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request / Response Schemas
class CreateSessionRequest(BaseModel):
    caller_id: Optional[str] = "Unknown"
    callee_id: Optional[str] = "Protected Callee"
    session_id: Optional[str] = None


class AddSegmentRequest(BaseModel):
    speaker: SpeakerType = SpeakerType.UNKNOWN
    text: str
    is_final: bool = True


class SimulateSessionRequest(BaseModel):
    chunks: Optional[List[str]] = None
    speaker: SpeakerType = SpeakerType.CALLER
    delay_seconds: float = 0.0


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
    """Add a transcript segment and process it through the streaming pipeline."""
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    segment = TranscriptSegment(
        session_id=session_id,
        speaker=payload.speaker,
        text=payload.text,
        is_final=payload.is_final,
    )
    result = await streaming_pipeline.process_segment(segment, broadcast=True)
    return result["segment"]


@app.post("/api/sessions/{session_id}/simulate", tags=["Simulation"])
async def simulate_session(session_id: str, payload: SimulateSessionRequest) -> Dict[str, Any]:
    """Run a mock streaming STT simulation through the RAKSHA pipeline."""
    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=payload.chunks,
        speaker=payload.speaker,
        delay_seconds=payload.delay_seconds,
        broadcast=True,
    )
    session = await session_store.get_session(session_id)
    return {
        "session_id": session_id,
        "steps_processed": len(results),
        "latest_risk": session.latest_risk.model_dump() if session and session.latest_risk else None,
        "summary": [
            {
                "utterance": r["segment"].text,
                "detected_tactics": [m.tactic.value for m in r["matches"]],
                "score": r["risk"].overall_score,
                "tier": r["risk"].risk_tier.value,
            }
            for r in results
        ],
    }


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
                if not isinstance(msg_dict, dict):
                    await websocket.send_text(
                        WSMessage(
                            type=WSMessageType.ERROR,
                            data={"error": "JSON payload must be an object"},
                        ).model_dump_json()
                    )
                    continue

                msg_type = msg_dict.get("type")

                if msg_type == WSMessageType.PING.value:
                    await websocket.send_text(
                        WSMessage(type=WSMessageType.PONG, data={"reply": "pong"}).model_dump_json()
                    )

                elif msg_type in [
                    WSMessageType.TRANSCRIPT_STREAM.value,
                    WSMessageType.TRANSCRIPT_UPDATE.value,
                ]:
                    payload = msg_dict.get("data", {})
                    if not isinstance(payload, dict):
                        await websocket.send_text(
                            WSMessage(
                                type=WSMessageType.ERROR,
                                data={"error": "Field 'data' must be an object"},
                            ).model_dump_json()
                        )
                        continue

                    speaker_raw = payload.get("speaker", SpeakerType.UNKNOWN.value)
                    try:
                        speaker = SpeakerType(speaker_raw)
                    except (ValueError, KeyError):
                        speaker = SpeakerType.UNKNOWN

                    text_val = payload.get("text", "")
                    if not isinstance(text_val, str) or not text_val.strip():
                        await websocket.send_text(
                            WSMessage(
                                type=WSMessageType.ERROR,
                                data={"error": "Field 'text' must be a non-empty string"},
                            ).model_dump_json()
                        )
                        continue

                    segment = TranscriptSegment(
                        session_id=session_id,
                        speaker=speaker,
                        text=text_val.strip(),
                        is_final=bool(payload.get("is_final", True)),
                    )
                    await streaming_pipeline.process_segment(segment, broadcast=True)

                else:
                    await websocket.send_text(
                        WSMessage(
                            type=WSMessageType.ERROR,
                            data={"error": f"Unsupported message type: {msg_type}"},
                        ).model_dump_json()
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
        logger.exception("Unexpected error in websocket loop for session %s: %s", session_id, exc)
        await manager.disconnect_session(session_id, websocket)
