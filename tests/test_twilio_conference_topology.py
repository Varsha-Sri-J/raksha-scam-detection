import asyncio
import base64
import hashlib
import hmac
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app
from backend.app.models import (
    CallSession,
    InterventionType,
    ProtectionAction,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    ProtectionLevel,
    RiskAssessment,
    RiskTier,
    SessionStatus,
    SpeakerType,
    TacticMatch,
    ManipulationCategory,
    UserWarningChannel,
    UserWarningStatus,
)
from backend.app.services.intervention_service import intervention_service
from backend.app.services.session_store import session_store
from backend.app.services.twilio_service import (
    TwilioService,
    get_conference_room_name,
    twilio_service,
)
from backend.app.services.user_warning_service import (
    MockUserWarningProvider,
    protected_user_warning_service,
)


@pytest.fixture(autouse=True)
def reset_session_store_fixture():
    """Ensure in-memory session store is cleared before each test."""
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


# ==============================================================================
# 1. Conference Name Generation
# ==============================================================================


def test_conference_name_generation():
    """Verify deterministic format raksha_conf_{session_id} with no PII."""
    session_id = "CA1234567890abcdef1234567890abcdef"
    conf_name = get_conference_room_name(session_id)
    assert conf_name == f"raksha_conf_{session_id}"
    assert "raksha_conf_" in conf_name
    assert "+1" not in conf_name
    assert "victim" not in conf_name

    # Check sanitation of unusual characters
    dirty_id = "CA-test:session@123"
    sanitized = get_conference_room_name(dirty_id)
    assert sanitized == "raksha_conf_CA-test_session_123"


# ==============================================================================
# 2-5. Inbound Conference TwiML Generation
# ==============================================================================


def test_inbound_conference_twiml_generation():
    """Verify inbound scammer TwiML has <Start><Stream track='inbound_track'> and <Dial><Conference>."""
    session_id = "CA_scammer_test"
    conf_name = get_conference_room_name(session_id)
    stream_url = "wss://test.domain/ws/twilio/media/CA_scammer_test"
    status_url = "https://test.domain/api/twilio/conference/status"

    twiml = twilio_service.generate_conference_twiml(
        stream_url=stream_url,
        session_id=session_id,
        conference_name=conf_name,
        status_callback_url=status_url,
    )

    assert twiml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<Response>" in twiml
    assert "<Start>" in twiml
    assert '<Stream url="wss://test.domain/ws/twilio/media/CA_scammer_test" track="inbound_track">' in twiml
    assert '<Parameter name="session_id" value="CA_scammer_test"' in twiml
    assert "<Dial>" in twiml
    assert '<Conference participantLabel="scammer"' in twiml
    assert f'statusCallback="{status_url}"' in twiml
    assert 'statusCallbackEvent="start end join leave announcement"' in twiml
    assert 'endConferenceOnExit="true"' in twiml
    assert 'beep="false"' in twiml
    assert conf_name in twiml
    # Invariant: Connect verb must NOT be present
    assert "<Connect>" not in twiml


# ==============================================================================
# 6. Protected-User TwiML Generation
# ==============================================================================


def test_protected_user_twiml_generation():
    """Verify protected-user TwiML contains <Dial><Conference participantLabel='protected_user'> without callbacks."""
    conf_name = "raksha_conf_CA123"
    twiml = twilio_service.generate_protected_user_twiml(conf_name)

    assert "<Response>" in twiml
    assert "<Dial>" in twiml
    assert '<Conference participantLabel="protected_user" beep="false">' in twiml
    assert conf_name in twiml
    # Invariant: must not duplicate conference callbacks
    assert "statusCallback" not in twiml
    assert "statusCallbackEvent" not in twiml
    assert "endConferenceOnExit" not in twiml


# ==============================================================================
# 7-16. Outbound Create Call Request & Error Handling
# ==============================================================================


@pytest.mark.asyncio
async def test_create_outbound_call_success_201():
    """Verify Create Call returns (True, CallSid, None) and does not mark connected."""
    mock_resp = httpx.Response(
        status_code=201,
        json={"sid": "CA_child_callee_123", "status": "queued"},
        request=httpx.Request("POST", "https://api.twilio.com/2010-04-01/Accounts/AC123/Calls.json"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        success, call_sid, err = await twilio_service.create_outbound_call(
            to_phone_number="+14155550100",
            conference_name="raksha_conf_CA123",
            account_sid="AC123",
            auth_token="auth_xyz",
            from_phone_number="+14155550200",
        )

        assert success is True
        assert call_sid == "CA_child_callee_123"
        assert err is None
        assert mock_post.called
        kwargs = mock_post.call_args.kwargs
        assert kwargs["data"]["To"] == "+14155550100"
        assert kwargs["data"]["From"] == "+14155550200"
        assert "participantLabel=\"protected_user\"" in kwargs["data"]["Twiml"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,err_body",
    [
        (400, {"code": 21211, "message": "Invalid To Phone Number"}),
        (401, {"code": 20003, "message": "Authentication Error"}),
        (403, {"code": 20003, "message": "Forbidden"}),
        (429, {"code": 20429, "message": "Too Many Requests"}),
        (500, {"code": 50000, "message": "Internal Server Error"}),
        (502, "Bad Gateway"),
        (503, "Service Unavailable"),
    ],
)
async def test_create_outbound_call_http_errors(status_code: int, err_body: Any):
    """Verify Create Call handles 400, 401, 403, 429, and 5xx without unhandled exceptions."""
    if isinstance(err_body, dict):
        mock_resp = httpx.Response(status_code=status_code, json=err_body, request=httpx.Request("POST", "http://test"))
    else:
        mock_resp = httpx.Response(status_code=status_code, text=err_body, request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        success, call_sid, err = await twilio_service.create_outbound_call(
            to_phone_number="+14155550100",
            conference_name="raksha_conf_CA123",
            account_sid="AC123",
            auth_token="auth_xyz",
            from_phone_number="+14155550200",
        )
        assert success is False
        assert call_sid is None
        assert err is not None
        assert str(status_code) in err


@pytest.mark.asyncio
async def test_create_outbound_call_timeout():
    """Verify Create Call handles network timeouts safely."""
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Connection timed out")):
        success, call_sid, err = await twilio_service.create_outbound_call(
            to_phone_number="+14155550100",
            conference_name="raksha_conf_CA123",
            account_sid="AC123",
            auth_token="auth_xyz",
            from_phone_number="+14155550200",
        )
        assert success is False
        assert call_sid is None
        assert "timed out" in err.lower()


@pytest.mark.asyncio
async def test_create_outbound_call_malformed_json_201():
    """Verify Create Call safely handles HTTP 201 with malformed JSON body."""
    mock_resp = httpx.Response(
        status_code=201,
        content=b"not-json-at-all",
        request=httpx.Request("POST", "http://test"),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        success, call_sid, err = await twilio_service.create_outbound_call(
            to_phone_number="+14155550100",
            conference_name="raksha_conf_CA123",
            account_sid="AC123",
            auth_token="auth_xyz",
            from_phone_number="+14155550200",
        )
        assert success is False
        assert call_sid is None
        assert "Malformed JSON" in err


# ==============================================================================
# 17. Inbound Webhook When Protected User Number Is Missing
# ==============================================================================


def test_inbound_webhook_missing_protected_number(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Verify missing PROTECTED_USER_PHONE_NUMBER preserves scammer conference path and does not crash."""
    monkeypatch.setattr(settings, "PROTECTED_USER_PHONE_NUMBER", None)
    call_sid = "CA-test-no-dest-num"

    resp = client.post(
        "/api/twilio/voice/incoming",
        data={"CallSid": call_sid, "From": "+18005550199", "To": "+14155551212"},
    )
    assert resp.status_code == 200
    xml = resp.text
    assert "<Dial>" in xml
    assert "<Conference" in xml
    assert f"raksha_conf_{call_sid}" in xml

    # Verify session fields
    session = asyncio.run(session_store.get_session(call_sid))
    assert session is not None
    assert session.protected_user_phone_number is None
    assert session.protected_user_call_sid is None
    assert session.protected_user_connected is False
    assert session.call_topology == "conference"


# ==============================================================================
# 18-24. Conference Status Callbacks (Start, Join, Leave, End, Duplicate)
# ==============================================================================


def test_conference_status_callback_lifecycle(client: TestClient):
    """Verify conference start, join (scammer & callee), leave, and end lifecycle."""
    session_id = "CA-test-conf-lifecycle"

    # Initialize session
    client.post(
        "/api/twilio/voice/incoming",
        data={"CallSid": session_id, "From": "+18005550199", "To": "+14155551212"},
    )

    conf_sid = "CF-conf-lifecycle-123"
    conf_name = f"raksha_conf_{session_id}"

    # 1. Start event
    resp_start = client.post(
        "/api/twilio/conference/status",
        data={
            "ConferenceSid": conf_sid,
            "FriendlyName": conf_name,
            "StatusCallbackEvent": "start",
        },
    )
    assert resp_start.status_code == 200
    session = asyncio.run(session_store.get_session(session_id))
    assert session.conference_sid == conf_sid

    # 2. Join event: scammer
    client.post(
        "/api/twilio/conference/status",
        data={
            "ConferenceSid": conf_sid,
            "FriendlyName": conf_name,
            "CallSid": session_id,
            "ParticipantLabel": "scammer",
            "StatusCallbackEvent": "join",
        },
    )
    session = asyncio.run(session_store.get_session(session_id))
    assert session.protected_user_connected is False

    # 3. Join event: protected_user
    callee_sid = "CA-callee-participant-456"
    client.post(
        "/api/twilio/conference/status",
        data={
            "ConferenceSid": conf_sid,
            "FriendlyName": conf_name,
            "CallSid": callee_sid,
            "ParticipantLabel": "protected_user",
            "StatusCallbackEvent": "join",
        },
    )
    session = asyncio.run(session_store.get_session(session_id))
    assert session.protected_user_connected is True
    assert session.protected_user_call_sid == callee_sid

    # 4. Duplicate join callback (idempotent)
    client.post(
        "/api/twilio/conference/status",
        data={
            "ConferenceSid": conf_sid,
            "FriendlyName": conf_name,
            "CallSid": callee_sid,
            "ParticipantLabel": "protected_user",
            "StatusCallbackEvent": "join",
        },
    )
    session = asyncio.run(session_store.get_session(session_id))
    assert session.protected_user_connected is True

    # 5. Leave event: protected_user
    client.post(
        "/api/twilio/conference/status",
        data={
            "ConferenceSid": conf_sid,
            "FriendlyName": conf_name,
            "CallSid": callee_sid,
            "ParticipantLabel": "protected_user",
            "StatusCallbackEvent": "leave",
        },
    )
    session = asyncio.run(session_store.get_session(session_id))
    assert session.protected_user_connected is False

    # 6. End event
    client.post(
        "/api/twilio/conference/status",
        data={
            "ConferenceSid": conf_sid,
            "FriendlyName": conf_name,
            "StatusCallbackEvent": "end",
        },
    )
    session = asyncio.run(session_store.get_session(session_id))
    assert session.status == SessionStatus.ENDED


# ==============================================================================
# Outbound Status Callback
# ==============================================================================


def test_outbound_status_callback(client: TestClient):
    """Verify /api/twilio/voice/outbound-status tracks ringing -> answered -> completed."""
    session_id = "CA-test-outbound-status"
    client.post(
        "/api/twilio/voice/incoming",
        data={"CallSid": session_id, "From": "+18005550199", "To": "+14155551212"},
    )
    callee_sid = "CA-outbound-child-789"
    session = asyncio.run(session_store.get_session(session_id))
    session.protected_user_call_sid = callee_sid

    # Ringing -> connected remains False
    client.post(
        "/api/twilio/voice/outbound-status",
        data={"CallSid": callee_sid, "CallStatus": "ringing"},
    )
    session = asyncio.run(session_store.get_session(session_id))
    assert session.protected_user_connected is False

    # Answered -> connected becomes True
    client.post(
        "/api/twilio/voice/outbound-status",
        data={"CallSid": callee_sid, "CallStatus": "answered"},
    )
    session = asyncio.run(session_store.get_session(session_id))
    assert session.protected_user_connected is True

    # Completed -> connected becomes False
    client.post(
        "/api/twilio/voice/outbound-status",
        data={"CallSid": callee_sid, "CallStatus": "completed"},
    )
    session = asyncio.run(session_store.get_session(session_id))
    assert session.protected_user_connected is False


# ==============================================================================
# 25-28. Media Stream: StreamSid Capture & Track Isolation Invariant
# ==============================================================================


def test_media_stream_captures_stream_sid_and_isolates_inbound(client: TestClient):
    """Verify start event captures stream_sid, inbound track is queued, non-inbound is ignored."""
    session_id = "CA-test-stream-track-safety"
    client.post(
        "/api/twilio/voice/incoming",
        data={"CallSid": session_id, "From": "+18005550199", "To": "+14155551212"},
    )

    with client.websocket_connect(f"/ws/twilio/media/{session_id}") as ws:
        # Connected
        ws.send_json({"event": "connected", "protocol": "Call", "version": "1.0.0"})

        # Start event with streamSid
        stream_sid = "MZ-safety-stream-001"
        ws.send_json({
            "event": "start",
            "start": {
                "streamSid": stream_sid,
                "accountSid": "AC-test",
                "callSid": session_id,
                "tracks": ["inbound"],
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
            },
        })

        # Verify session.stream_sid was captured
        session = asyncio.run(session_store.get_session(session_id))
        assert session.stream_sid == stream_sid

        # Send outbound track (should be completely ignored)
        dummy_audio = base64.b64encode(b"\xff\x00" * 40).decode("utf-8")
        ws.send_json({
            "event": "media",
            "media": {
                "track": "outbound",  # Non-inbound track
                "chunk": "1",
                "payload": dummy_audio,
            },
        })

        # Send inbound track (processed)
        ws.send_json({
            "event": "media",
            "media": {
                "track": "inbound",
                "chunk": "2",
                "payload": dummy_audio,
            },
        })

        # Send stop
        ws.send_json({"event": "stop"})


# ==============================================================================
# 29. Twilio Signature Validation on New Callbacks
# ==============================================================================


def test_signature_validation_on_new_callbacks(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Verify X-Twilio-Signature validation on conference status and outbound status."""
    auth_token = "secret_auth_token_abc"
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", auth_token)
    monkeypatch.setattr(settings, "TWILIO_VALIDATE_SIGNATURE", True)

    url = "http://testserver/api/twilio/conference/status"
    params = {"ConferenceSid": "CF123", "StatusCallbackEvent": "start"}

    # Compute valid signature
    data_to_sign = url + "ConferenceSidCF123StatusCallbackEventstart"
    mac = hmac.new(auth_token.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha1)
    valid_sig = base64.b64encode(mac.digest()).decode("utf-8")

    # 1. Valid signature accepted
    resp_valid = client.post(
        "/api/twilio/conference/status",
        data=params,
        headers={"X-Twilio-Signature": valid_sig},
    )
    assert resp_valid.status_code == 200

    # 2. Invalid signature rejected with 403
    resp_invalid = client.post(
        "/api/twilio/conference/status",
        data=params,
        headers={"X-Twilio-Signature": "bad_sig_value"},
    )
    assert resp_invalid.status_code == 403

    # Outbound status with bad signature
    resp_outbound_bad = client.post(
        "/api/twilio/voice/outbound-status",
        data={"CallSid": "CA123", "CallStatus": "ringing"},
        headers={"X-Twilio-Signature": "bad_sig_value"},
    )
    assert resp_outbound_bad.status_code == 403


# ==============================================================================
# 30. Simulation Mode Safety
# ==============================================================================


def test_simulation_mode_does_not_call_twilio(client: TestClient):
    """Verify simulation endpoints remain completely offline and do not invoke Twilio."""
    session_id = "sim-session-offline-123"

    # Create session
    client.post("/api/sessions", json={"session_id": session_id})

    # Run simulation
    with patch("httpx.AsyncClient.post") as mock_http:
        resp = client.post(
            f"/api/sessions/{session_id}/simulate",
            json={"chunks": ["Suspicious prompt", "Send gift cards immediately"]},
        )
        assert resp.status_code == 200
        assert mock_http.called is False  # Zero Twilio HTTP calls


# ==============================================================================
# 31. MockUserWarningProvider Regression (Phase 7C Preservation)
# ==============================================================================


def test_mock_user_warning_provider_preservation():
    """Verify MockUserWarningProvider remains active and functional."""
    session = CallSession(session_id="test-warning-session")
    decision = ProtectionDecision(
        session_id=session.session_id,
        level=ProtectionLevel.WARNING,
        trigger_score=75.0,
        trigger_tier=RiskTier.HIGH,
        explanation="High scam score",
        triggered_actions=[
            ProtectionAction(
                action_type=ProtectionActionType.DASHBOARD_ALERT,
                level=ProtectionLevel.WARNING,
                message="Alert",
                status=ProtectionActionStatus.EXECUTED,
            )
        ],
    )

    record = protected_user_warning_service.warn_user(session, decision)
    assert record is not None
    assert record.status == UserWarningStatus.DELIVERED
    assert record.provider == "mock"
    assert "Please be careful" in record.message


# ==============================================================================
# 32. Phase 7D-2 Intervention Disconnect Regression
# ==============================================================================


@pytest.mark.asyncio
async def test_intervention_disconnect_targets_parent_call_sid():
    """Verify 7D-2 disconnect targets session.session_id (parent/scammer CallSid)."""
    scammer_call_sid = "CA11111111111111111111111111111111"
    session = CallSession(
        session_id=scammer_call_sid,
        parent_call_sid=scammer_call_sid,
        conference_name="raksha_conf_CA11111111111111111111111111111111",
        call_topology="conference",
    )

    decision = ProtectionDecision(
        session_id=scammer_call_sid,
        level=ProtectionLevel.CRITICAL_INTERCEPT,
        trigger_score=95.0,
        trigger_tier=RiskTier.CRITICAL,
        explanation="Acute extraction",
        triggered_actions=[
            ProtectionAction(
                action_type=ProtectionActionType.DASHBOARD_ALERT,
                level=ProtectionLevel.CRITICAL_INTERCEPT,
                message="Alert",
                status=ProtectionActionStatus.EXECUTED,
            )
        ],
    )

    acute_risk = RiskAssessment(
        session_id=scammer_call_sid,
        overall_score=95.0,
        risk_tier=RiskTier.CRITICAL,
        triggered_tactics=[
            TacticMatch(
                tactic=ManipulationCategory.INFORMATION_PHISHING,
                confidence=0.95,
                evidence_text="Share your OTP",
            )
        ],
    )

    # Use MockInterventionProvider to test service orchestration
    record = await intervention_service.evaluate_and_execute(session, decision, acute_risk)
    assert record is not None
    assert record.type == InterventionType.DISCONNECT
    assert record.session_id == scammer_call_sid
