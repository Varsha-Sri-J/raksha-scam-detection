import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.models import (
    CallSession,
    CaregiverContact,
    RiskAssessment,
    SessionStatus,
    SpeakerType,
    TranscriptSegment,
    UserWarningStatus,
    WSMessage,
    WSMessageType,
)
from backend.app.risk_engine import risk_engine
from backend.app.services.connection_manager import manager
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.session_store import session_store
from backend.app.services.stt import get_stt_provider
from backend.app.services.twilio_service import get_conference_room_name, twilio_service

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
    caregiver_contacts: Optional[List[CaregiverContact]] = None


class AddSegmentRequest(BaseModel):
    speaker: SpeakerType = SpeakerType.UNKNOWN
    text: str
    is_final: bool = True


class SimulateSessionRequest(BaseModel):
    chunks: Optional[List[str]] = None
    speaker: SpeakerType = SpeakerType.CALLER
    delay_seconds: float = 0.0
    callee_id: Optional[str] = None
    caller_id: Optional[str] = None
    caregiver_contacts: Optional[List[CaregiverContact]] = None


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
        caregiver_contacts=payload.caregiver_contacts,
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
    session = await session_store.get_session(session_id)
    callee = payload.callee_id if payload.callee_id is not None else (session.callee_id if session else "Protected Callee")
    caregivers = payload.caregiver_contacts
    if caregivers is None and (callee == "Lakshmi R." or (session and session.callee_id == "Lakshmi R.")):
        caregivers = [
            CaregiverContact(
                name="Ananya R.",
                phone_number="+91 91234 56789",
                relationship="Daughter",
                enabled=True,
            )
        ]

    if not session:
        session = await session_store.create_session(
            session_id=session_id,
            caller_id=payload.caller_id if payload.caller_id is not None else "Unknown",
            callee_id=callee,
            caregiver_contacts=caregivers,
        )
    else:
        if payload.callee_id is not None:
            session.callee_id = payload.callee_id
        if payload.caller_id is not None:
            session.caller_id = payload.caller_id
        if caregivers is not None:
            session.caregiver_contacts = caregivers

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


# --- Twilio Voice Webhooks & Media Stream (Phase 5A) ---


async def _parse_form_payload(request: Request) -> Dict[str, str]:
    """Parse application/x-www-form-urlencoded or JSON request body safely without extra dependencies."""
    body_bytes = await request.body()
    if not body_bytes:
        return {}
    body_text = body_bytes.decode("utf-8", errors="replace")
    # 1. Try urlencoded form parsing (Twilio standard)
    parsed = parse_qs(body_text)
    if parsed:
        return {k: v[0] if isinstance(v, list) and len(v) > 0 else "" for k, v in parsed.items()}
    # 2. Try JSON fallback
    try:
        json_obj = json.loads(body_text)
        if isinstance(json_obj, dict):
            return {str(k): str(v) for k, v in json_obj.items()}
    except Exception:
        pass
    return {}


@app.post("/api/twilio/voice/incoming", tags=["Twilio"])
async def twilio_incoming_voice(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
) -> Response:
    """Twilio Voice webhook for inbound calls (Phase 7D-3).

    Initializes a CallSession for the CallSid with Conference topology.
    Returns TwiML instructions to:
      1. Asynchronously fork inbound caller audio to the Media Stream WebSocket (<Start><Stream track="inbound_track">).
      2. Bridge the inbound caller into the shared conference room (<Dial><Conference participantLabel="scammer">).
    Simultaneously dispatches an outbound call to the protected user (if configured)
    to place them into the same conference.
    """
    form_data = await _parse_form_payload(request)
    call_sid = form_data.get("CallSid", "")
    if not call_sid:
        raise HTTPException(status_code=400, detail="Missing CallSid in request")

    from_number = form_data.get("From", "Unknown")
    to_number = form_data.get("To", "Protected Callee")

    # Validate signature if configured
    if not twilio_service.verify_twilio_signature(
        str(request.url), form_data, x_twilio_signature
    ):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    conference_name = get_conference_room_name(call_sid)

    # Create or retrieve CallSession using CallSid as session_id
    session = await session_store.get_session(call_sid)
    if not session:
        session = await session_store.create_session(
            session_id=call_sid,
            caller_id=from_number or "Unknown",
            callee_id=to_number or "Protected Callee",
        )
        baseline_risk = risk_engine.evaluate_session(session)
        await session_store.update_risk_assessment(call_sid, baseline_risk)
        session.latest_risk = baseline_risk

    # Update conference and topology metadata on session
    session.parent_call_sid = call_sid
    session.conference_name = conference_name
    session.call_topology = "conference"
    session.protected_user_phone_number = settings.PROTECTED_USER_PHONE_NUMBER
    session.protected_user_connected = False

    # Derive WebSocket stream URL
    if settings.TWILIO_STREAM_BASE_URL:
        stream_url = f"{settings.TWILIO_STREAM_BASE_URL.rstrip('/')}/ws/twilio/media/{call_sid}"
    else:
        ws_scheme = "wss" if request.url.scheme == "https" else "ws"
        stream_url = f"{ws_scheme}://{request.url.netloc}/ws/twilio/media/{call_sid}"

    # Derive Conference and Outbound Status Callback URLs
    http_scheme = request.url.scheme
    conf_status_url = f"{http_scheme}://{request.url.netloc}/api/twilio/conference/status"
    outbound_status_url = f"{http_scheme}://{request.url.netloc}/api/twilio/voice/outbound-status"

    twiml_content = twilio_service.generate_conference_twiml(
        stream_url=stream_url,
        session_id=call_sid,
        conference_name=conference_name,
        status_callback_url=conf_status_url,
    )

    # Asynchronously dispatch outbound call to protected user if destination number is configured
    protected_dest = settings.PROTECTED_USER_PHONE_NUMBER
    if protected_dest and protected_dest.strip():
        async def _dispatch_protected_user_call():
            try:
                success, callee_call_sid, err = await twilio_service.create_outbound_call(
                    to_phone_number=protected_dest.strip(),
                    conference_name=conference_name,
                    status_callback_url=outbound_status_url,
                )
                if success and callee_call_sid:
                    session.protected_user_call_sid = callee_call_sid
                    logger.info(
                        "Dispatched protected user outbound call %s for session %s",
                        callee_call_sid,
                        call_sid,
                    )
                else:
                    logger.warning(
                        "Failed to dispatch protected user call for session %s: %s",
                        call_sid,
                        err,
                    )
            except Exception as exc:
                logger.exception(
                    "Unexpected error dispatching protected user call for session %s: %s",
                    call_sid,
                    exc,
                )

        asyncio.create_task(_dispatch_protected_user_call())
    else:
        logger.warning(
            "PROTECTED_USER_PHONE_NUMBER not configured; skipping outbound call for session %s",
            call_sid,
        )

    return Response(content=twiml_content, media_type="application/xml")


@app.post("/api/twilio/voice/outbound-status", tags=["Twilio"])
async def twilio_outbound_status(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
) -> Dict[str, Any]:
    """Twilio Voice status callback webhook for the protected user outbound leg.

    Tracks call state transitions (ringing, answered, completed, etc.)
    and updates protected_user_connected state.
    """
    form_data = await _parse_form_payload(request)
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")

    if not twilio_service.verify_twilio_signature(
        str(request.url), form_data, x_twilio_signature
    ):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    session = await session_store.find_session_by_conference(call_sid=call_sid)
    if session:
        call_status_lower = call_status.lower()
        if call_status_lower in ["answered", "in-progress"]:
            session.protected_user_connected = True
            logger.info(
                "Protected user answered call %s for session %s",
                call_sid,
                session.session_id,
            )
        elif call_status_lower in ["completed", "failed", "busy", "no-answer", "canceled"]:
            session.protected_user_connected = False
            logger.info(
                "Protected user call %s ended with status %s for session %s",
                call_sid,
                call_status,
                session.session_id,
            )

    return {
        "status": "ok",
        "call_sid": call_sid,
        "call_status": call_status,
    }


@app.post("/api/twilio/conference/status", tags=["Twilio"])
async def twilio_conference_status(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
) -> Dict[str, Any]:
    """Twilio Conference status callback webhook.

    Authoritative for conference lifecycle because scammer leg configures:
    statusCallbackEvent="start end join leave announcement"
    """
    form_data = await _parse_form_payload(request)
    conf_sid = form_data.get("ConferenceSid", "")
    friendly_name = form_data.get("FriendlyName", "")
    call_sid = form_data.get("CallSid", "")
    participant_label = form_data.get("ParticipantLabel", "")
    event = form_data.get("StatusCallbackEvent", "")
    announcement_status = form_data.get("AnnouncementStatus", "")

    if not twilio_service.verify_twilio_signature(
        str(request.url), form_data, x_twilio_signature
    ):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    session = await session_store.find_session_by_conference(
        conference_name=friendly_name,
        conference_sid=conf_sid,
        call_sid=call_sid,
    )

    if session:
        if conf_sid and not session.conference_sid:
            session.conference_sid = conf_sid

        if event == "start":
            logger.info(
                "Conference %s (%s) started for session %s",
                conf_sid,
                friendly_name,
                session.session_id,
            )

        elif event == "join":
            logger.info(
                "Participant %s (%s) joined conference %s for session %s",
                call_sid,
                participant_label,
                conf_sid,
                session.session_id,
            )
            if participant_label == "protected_user":
                session.protected_user_connected = True
                if not session.protected_user_call_sid and call_sid:
                    session.protected_user_call_sid = call_sid

        elif event == "leave":
            logger.info(
                "Participant %s (%s) left conference %s for session %s",
                call_sid,
                participant_label,
                conf_sid,
                session.session_id,
            )
            if participant_label == "protected_user":
                session.protected_user_connected = False

        elif event == "end":
            logger.info("Conference %s ended for session %s", conf_sid, session.session_id)
            session.protected_user_connected = False
            ended_session = await session_store.end_session(session.session_id)
            if ended_session:
                await manager.broadcast_session(
                    session.session_id,
                    WSMessage(
                        type=WSMessageType.SESSION_STATUS,
                        data={"status": SessionStatus.ENDED.value},
                    ),
                )

        elif event == "announcement":
            logger.info(
                "Announcement callback on conference %s for participant %s: status=%s",
                conf_sid,
                call_sid,
                announcement_status,
            )
            # User Correction 2: Extract warning_id from AnnouncementUrl or query params
            # for deterministic correlation. Never update based on position or timing.
            announce_url_param = (
                form_data.get("AnnouncementUrl") or form_data.get("AnnounceUrl") or ""
            )
            parsed_warning_id = None
            if announce_url_param:
                parsed_url = urlparse(announce_url_param)
                query_params = parse_qs(parsed_url.query)
                if "warning_id" in query_params and query_params["warning_id"]:
                    parsed_warning_id = query_params["warning_id"][0]

            if not parsed_warning_id:
                parsed_warning_id = form_data.get("WarningId") or request.query_params.get("warning_id")

            if not parsed_warning_id:
                logger.warning(
                    "Announcement callback on conference %s lacks deterministic warning_id correlation; leaving warning records untouched",
                    conf_sid,
                )
            elif (
                call_sid
                and session.protected_user_call_sid
                and call_sid != session.protected_user_call_sid
            ):
                logger.warning(
                    "Announcement callback participant %s does not match protected_user_call_sid %s; skipping correlation",
                    call_sid,
                    session.protected_user_call_sid,
                )
            else:
                status_norm = (announcement_status or form_data.get("Status") or "").strip().lower()
                if status_norm in ["completed", "announcement-end", "success", "delivered"]:
                    updated = await session_store.update_user_warning_status(
                        session.session_id,
                        warning_id=parsed_warning_id,
                        status=UserWarningStatus.DELIVERED,
                    )
                    if updated:
                        logger.info(
                            "Deterministic correlation: marked warning %s as DELIVERED for session %s",
                            parsed_warning_id,
                            session.session_id,
                        )
                    else:
                        logger.warning(
                            "Warning %s not found in history for session %s; leaving records untouched",
                            parsed_warning_id,
                            session.session_id,
                        )
                elif status_norm in ["failed", "announcement-fail", "canceled", "error"]:
                    err_msg = (
                        form_data.get("ErrorMessage") or f"Announcement failed with status {status_norm}"
                    )
                    updated = await session_store.update_user_warning_status(
                        session.session_id,
                        warning_id=parsed_warning_id,
                        status=UserWarningStatus.FAILED,
                        error=err_msg,
                    )
                    if updated:
                        logger.info(
                            "Deterministic correlation: marked warning %s as FAILED for session %s",
                            parsed_warning_id,
                            session.session_id,
                        )
                    else:
                        logger.warning(
                            "Warning %s not found in history for session %s; leaving records untouched",
                            parsed_warning_id,
                            session.session_id,
                        )
                else:
                    logger.warning(
                        "Announcement callback on conference %s for session %s has ambiguous status '%s'; leaving warning records untouched",
                        conf_sid,
                        session.session_id,
                        status_norm,
                    )

    return {
        "status": "ok",
        "conference_sid": conf_sid,
        "event": event,
    }


@app.post("/api/twilio/voice/warning-twiml/{session_id}", tags=["Twilio"])
async def twilio_warning_twiml(
    session_id: str,
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
) -> Response:
    """Twilio Voice webhook delivering canonical protected-user warning TwiML.

    Executed strictly by Twilio Conference Participant AnnounceUrl on the protected-user leg.
    Guarantees:
    - Validates Twilio signature using twilio_service.verify_twilio_signature.
    - Resolves CallSession; returns 404 if not found.
    - Resolves canonical warning message from session's existing protected-user warning state.
    - Returns 400 if no canonical warning exists (never invents text).
    - Ignores arbitrary text or risk score inputs from HTTP query/body parameters.
    - Returns XML with <Say voice="Polly.Aditi" language="en-IN">.
    """
    form_data = await _parse_form_payload(request)

    # 1. Validate Twilio signature
    if not twilio_service.verify_twilio_signature(
        str(request.url), form_data, x_twilio_signature
    ):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    # 2. Resolve CallSession
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"CallSession {session_id} not found")

    # 3. Determine canonical warning from session's existing protected-user warning history
    if not session.user_warning_history:
        logger.warning(
            "Rejecting warning TwiML request for session %s: No active canonical warning found",
            session_id,
        )
        raise HTTPException(
            status_code=400,
            detail=f"No active canonical warning found for session {session_id}",
        )

    # Retrieve canonical warning message from warning record
    warning_id = request.query_params.get("warning_id")
    target_record = None
    if warning_id:
        for rec in reversed(session.user_warning_history):
            if rec.warning_id == warning_id:
                target_record = rec
                break

    if not target_record:
        target_record = session.user_warning_history[-1]

    canonical_message = target_record.message
    twiml_content = twilio_service.generate_warning_twiml(canonical_message)

    return Response(content=twiml_content, media_type="application/xml")


@app.post("/api/twilio/voice/status", tags=["Twilio"])
async def twilio_voice_status(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
) -> Dict[str, Any]:
    """Twilio Voice status callback webhook for inbound parent leg.

    Tracks call state transitions and marks sessions as ENDED when completed.
    """
    form_data = await _parse_form_payload(request)
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")

    if not twilio_service.verify_twilio_signature(
        str(request.url), form_data, x_twilio_signature
    ):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    terminal_statuses = {"completed", "failed", "busy", "no-answer", "canceled"}
    if call_status.lower() in terminal_statuses:
        session = await session_store.end_session(call_sid)
        if session:
            await manager.broadcast_session(
                call_sid,
                WSMessage(
                    type=WSMessageType.SESSION_STATUS,
                    data={"status": SessionStatus.ENDED.value},
                ),
            )
            logger.info("Twilio call %s ended with status %s", call_sid, call_status)

    return {
        "status": "ok",
        "session_id": call_sid,
        "call_status": call_status,
    }


@app.websocket("/ws/twilio/media/{session_id}")
async def twilio_media_stream_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Twilio Media Stream WebSocket endpoint for receiving live call audio frames.

    Phase 5B connects incoming μ-law audio frames to the STT provider (Deepgram or Mock)
    via a bounded async queue, and feeds resulting TranscriptSegments into the StreamingPipeline.
    """
    await websocket.accept()
    logger.info("Twilio Media Stream connected for session %s", session_id)

    # 1. Ensure session exists in session_store
    session = await session_store.get_session(session_id)
    if not session:
        session = await session_store.create_session(session_id=session_id)
        baseline_risk = risk_engine.evaluate_session(session)
        await session_store.update_risk_assessment(session_id, baseline_risk)
        session.latest_risk = baseline_risk

    # 2. Bounded audio queue (maxsize=500: ~10 seconds of 20ms frames)
    audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=500)
    stt_failed = False
    overflow_count = 0

    # 3. Audio stream consumer generator
    async def audio_stream_generator():
        while True:
            chunk = await audio_queue.get()
            if chunk is None:  # EOF sentinel
                break
            yield chunk

    # 4. STT bridge worker task
    async def run_stt_worker():
        nonlocal stt_failed
        try:
            stt_provider = get_stt_provider()
            async for segment in stt_provider.stream_transcripts(
                session_id=session_id,
                input_data=audio_stream_generator(),
                speaker=SpeakerType.CALLER,
            ):
                logger.info("STT segment received for session %s: %s", session_id, segment.text)
                await streaming_pipeline.process_segment(segment, broadcast=True)
        except asyncio.CancelledError:
            logger.info("STT worker cancelled for session %s", session_id)
            raise
        except Exception as exc:
            stt_failed = True
            logger.exception("STT bridge failure for session %s: %s", session_id, exc)
            # Drain queue to release buffered audio memory immediately
            while not audio_queue.empty():
                try:
                    audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            await manager.broadcast_session(
                session_id,
                WSMessage(
                    type=WSMessageType.ERROR,
                    data={"session_id": session_id, "error": f"STT bridge error: {str(exc)}"},
                ),
            )

    stt_task = asyncio.create_task(run_stt_worker())

    async def shutdown_stt_worker(graceful: bool = True) -> None:
        """Safely shut down the STT worker task without leaking tasks or raising CancelledError."""
        if stt_task.done():
            return

        if graceful and not stt_failed:
            # Signal EOF to audio generator
            try:
                audio_queue.put_nowait(None)
            except asyncio.QueueFull:
                try:
                    audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                audio_queue.put_nowait(None)

            # Bounded grace period for STT provider & pipeline to finish processing
            try:
                await asyncio.wait([stt_task], timeout=2.0)
            except (asyncio.CancelledError, Exception):
                pass

            if stt_task.done():
                return

        # If abrupt, ungraceful, or grace period exceeded, cancel STT worker safely
        if not stt_task.done():
            stt_task.cancel()
            try:
                await asyncio.shield(stt_task)
            except (asyncio.CancelledError, Exception):
                pass

    try:
        while True:
            raw_data = await websocket.receive_text()
            event_type, msg_dict = twilio_service.parse_media_stream_message(raw_data)
            if event_type is None or msg_dict is None:
                logger.warning(
                    "Received malformed Twilio media stream message on session %s",
                    session_id,
                )
                continue

            if event_type == "connected":
                logger.info(
                    "Twilio Media Stream protocol %s connected for session %s",
                    msg_dict.get("protocol"),
                    session_id,
                )

            elif event_type == "start":
                start_data = msg_dict.get("start", {})
                stream_sid = start_data.get("streamSid")
                if session and stream_sid:
                    session.stream_sid = stream_sid
                logger.info(
                    "Twilio Media Stream started: streamSid=%s for session %s",
                    stream_sid,
                    session_id,
                )

            elif event_type == "media":
                logger.debug("Received media frame on session %s", session_id)
                # If STT worker has failed permanently, do not queue new audio
                if stt_failed:
                    continue

                media_data = msg_dict.get("media", {})
                track = media_data.get("track", "inbound")

                # Currently supported: inbound caller track
                if track != "inbound":
                    logger.debug("Ignoring unsupported track '%s' on session %s", track, session_id)
                    continue

                payload_b64 = media_data.get("payload", "")
                audio_bytes = twilio_service.decode_media_payload(payload_b64)
                if audio_bytes is None:
                    logger.warning(
                        "Received invalid base64 media payload on session %s", session_id
                    )
                    continue

                # Bounded queue push with explicit overflow handling
                try:
                    audio_queue.put_nowait(audio_bytes)
                except asyncio.QueueFull:
                    overflow_count += 1
                    if overflow_count == 1 or overflow_count % 50 == 0:
                        logger.warning(
                            "Twilio audio queue full for session %s. Dropped %d frame(s).",
                            session_id,
                            overflow_count,
                        )

            elif event_type == "stop":
                logger.info("Twilio media stream stop received for session %s", session_id)
                await shutdown_stt_worker(graceful=True)
                break

    except WebSocketDisconnect:
        logger.info("Twilio Media Stream client disconnected for session %s", session_id)
    except asyncio.CancelledError:
        logger.info("Twilio Media Stream session cancelled for session %s", session_id)
    except Exception as exc:
        logger.warning(
            "Unexpected error in Twilio Media Stream for session %s: %s",
            session_id,
            exc,
        )
    finally:
        try:
            await shutdown_stt_worker(graceful=False)
        except (asyncio.CancelledError, Exception):
            pass
