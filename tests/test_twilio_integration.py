import base64
import hashlib
import hmac
import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app
from backend.app.models import SessionStatus
from backend.app.services.session_store import session_store
from backend.app.services.stt import MockSTTProvider
from backend.app.services.twilio_service import TwilioService, twilio_service


# --- Test 1: Incoming Webhook Creates Session and Returns TwiML ---


def test_incoming_webhook_creates_session_and_returns_twiml(client: TestClient):
    """Verify POST /api/twilio/voice/incoming initializes session and returns valid TwiML XML."""
    call_sid = "CA-test-incoming-001"
    caller = "+18005550199"
    callee = "+14155551212"

    response = client.post(
        "/api/twilio/voice/incoming",
        data={
            "CallSid": call_sid,
            "From": caller,
            "To": callee,
            "CallStatus": "ringing",
        },
    )

    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    xml_content = response.text
    assert "<Response>" in xml_content
    assert "<Connect>" in xml_content or ("<Start>" in xml_content and "<Conference" in xml_content)
    assert "<Stream" in xml_content
    assert f"/ws/twilio/media/{call_sid}" in xml_content
    assert f'value="{call_sid}"' in xml_content

    # Verify session was created in session_store with CallSid as session_id
    get_resp = client.get(f"/api/sessions/{call_sid}")
    assert get_resp.status_code == 200
    session_data = get_resp.json()
    assert session_data["session_id"] == call_sid
    assert session_data["caller_id"] == caller
    assert session_data["callee_id"] == callee
    assert session_data["status"] == SessionStatus.ACTIVE.value


# --- Test 2: Status Callback Ends Session on Terminal Call Statuses ---


def test_status_callback_completed_ends_session(client: TestClient):
    """Verify POST /api/twilio/voice/status with CallStatus='completed' marks session as ENDED."""
    call_sid = "CA-test-status-completed"

    # 1. Initialize session via incoming webhook
    client.post(
        "/api/twilio/voice/incoming",
        data={"CallSid": call_sid, "From": "+111", "To": "+222"},
    )

    # 2. Fire completed status callback
    status_resp = client.post(
        "/api/twilio/voice/status",
        data={"CallSid": call_sid, "CallStatus": "completed"},
    )
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "ok"
    assert data["session_id"] == call_sid

    # 3. Verify session is now ENDED
    session_resp = client.get(f"/api/sessions/{call_sid}")
    assert session_resp.status_code == 200
    assert session_resp.json()["status"] == SessionStatus.ENDED.value


def test_status_callback_busy_and_failed_statuses(client: TestClient):
    """Verify terminal statuses (busy, failed, no-answer) also end the session."""
    for terminal_status in ["busy", "failed", "no-answer", "canceled"]:
        call_sid = f"CA-test-status-{terminal_status}"
        client.post(
            "/api/twilio/voice/incoming",
            data={"CallSid": call_sid, "From": "+111", "To": "+222"},
        )

        resp = client.post(
            "/api/twilio/voice/status",
            data={"CallSid": call_sid, "CallStatus": terminal_status},
        )
        assert resp.status_code == 200

        sess = client.get(f"/api/sessions/{call_sid}").json()
        assert sess["status"] == SessionStatus.ENDED.value


# --- Test 3: Twilio Media Stream WebSocket Lifecycle ---


def test_twilio_media_stream_lifecycle(client: TestClient):
    """Verify /ws/twilio/media/{session_id} accepts connected, start, media, and stop frames."""
    session_id = "CA-test-media-stream-lifecycle"

    with client.websocket_connect(f"/ws/twilio/media/{session_id}") as ws:
        # 1. Connected event
        ws.send_json({
            "event": "connected",
            "protocol": "Call",
            "version": "1.0.0",
        })

        # 2. Start event
        ws.send_json({
            "event": "start",
            "sequenceNumber": "1",
            "start": {
                "streamSid": "MZ-stream-001",
                "accountSid": "AC-test-account",
                "callSid": session_id,
                "tracks": ["inbound"],
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1,
                },
            },
        })

        # 3. Media event (valid base64 mulaw audio chunk)
        dummy_audio = b"\xff\x00\xaa\x55" * 40
        b64_audio = base64.b64encode(dummy_audio).decode("utf-8")
        ws.send_json({
            "event": "media",
            "sequenceNumber": "2",
            "media": {
                "track": "inbound",
                "chunk": "1",
                "timestamp": "12345",
                "payload": b64_audio,
            },
        })

        # 4. Stop event (gracefully breaks loop)
        ws.send_json({
            "event": "stop",
            "sequenceNumber": "3",
            "stop": {
                "accountSid": "AC-test-account",
                "callSid": session_id,
            },
        })


# --- Test 4: Media Stream Malformed Input Handling ---


def test_twilio_media_stream_malformed_handling(client: TestClient):
    """Verify WebSocket safely handles non-JSON, missing fields, and bad base64."""
    session_id = "CA-test-media-malformed"

    with client.websocket_connect(f"/ws/twilio/media/{session_id}") as ws:
        # Send raw invalid string
        ws.send_text("not json at all")

        # Send JSON without 'event' field
        ws.send_json({"no_event": "here"})

        # Send media event with corrupt base64
        ws.send_json({
            "event": "media",
            "media": {"payload": "invalid-base64-!@#$%^&*()"},
        })

        # Send stop to close cleanly
        ws.send_json({"event": "stop"})


# --- Test 5: Signature Validation Logic ---


def test_twilio_signature_validation_algorithm():
    """Verify Twilio HMAC-SHA1 signature verification logic directly."""
    auth_token = "test_secret_token_123"
    svc = TwilioService(auth_token=auth_token, validate_signature=True)

    url = "https://example.com/api/twilio/voice/incoming"
    params = {
        "CallSid": "CA12345",
        "From": "+18005550199",
        "To": "+14155551212",
    }

    # Compute expected signature: url + k1 + v1 + k2 + v2 ...
    data_to_sign = url + "CallSidCA12345From+18005550199To+14155551212"
    mac = hmac.new(auth_token.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha1)
    valid_sig = base64.b64encode(mac.digest()).decode("utf-8")

    # 1. Valid signature returns True
    assert svc.verify_twilio_signature(url, params, valid_sig) is True

    # 2. Tampered signature returns False
    assert svc.verify_twilio_signature(url, params, "invalid_signature_xxx") is False

    # 3. Missing signature returns False when validation is True
    assert svc.verify_twilio_signature(url, params, None) is False

    # 4. When validation is disabled, always returns True
    svc_disabled = TwilioService(auth_token=auth_token, validate_signature=False)
    assert svc_disabled.verify_twilio_signature(url, params, "any_bad_sig") is True


# --- Test 6: Mock Mode and Offline Pipeline Preservation ---


def test_mock_mode_and_offline_preservation():
    """Verify MockSTTProvider and default settings remain intact and offline."""
    assert settings.STT_PROVIDER == "mock"
    mock_stt = MockSTTProvider()
    assert len(mock_stt.DEFAULT_SCAM_CHUNKS) == 5
    assert mock_stt.DEFAULT_SCAM_CHUNKS[0].startswith("This is Officer Miller")
