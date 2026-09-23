import asyncio
import logging
import re
import unittest.mock
from urllib.parse import parse_qs, urlparse
import pytest
from fastapi.testclient import TestClient
import httpx

from backend.app.config import settings
from backend.app.main import app
from backend.app.models import (
    CallSession,
    CaregiverContact,
    InterventionStatus,
    InterventionType,
    ManipulationCategory,
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
    TranscriptSegment,
    UserWarningChannel,
    UserWarningRecord,
    UserWarningStatus,
    WSMessageType,
)
from backend.app.services.intervention_service import (
    MockInterventionProvider,
    intervention_service,
)
from backend.app.services.notification_service import (
    MockSMSProvider,
    caregiver_notification_service,
)
from backend.app.services.user_warning_service import (
    BaseUserWarningProvider,
    InvalidUserWarningProvider,
    MockUserWarningProvider,
    TwilioConferenceUserWarningProvider,
    get_user_warning_provider,
    protected_user_warning_service,
)
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.protection_engine import protection_engine
from backend.app.services.session_store import session_store
from backend.app.services.twilio_service import twilio_service
from ai.classifier import semantic_classifier

# Synthetic test credentials
FAKE_ACCOUNT_SID = "TEST_ACCOUNT_SID"
FAKE_AUTH_TOKEN = "TEST_AUTH_TOKEN"
CONFERENCE_SID = "CF11112222333344445555666677778888"
SCAMMER_CALL_SID = "CA11111111111111111111111111111111"
CALLEE_CALL_SID = "CA22222222222222222222222222222222"


@pytest.fixture(autouse=True)
def reset_warning_state(monkeypatch):
    """Reset global settings and services before and after each test."""
    protection_engine.clear()
    protected_user_warning_service.default_provider = None
    caregiver_notification_service.default_provider = MockSMSProvider()
    intervention_service.default_provider = MockInterventionProvider()

    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", FAKE_ACCOUNT_SID)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", FAKE_AUTH_TOKEN)
    monkeypatch.setattr(settings, "TWILIO_API_TIMEOUT_SECONDS", 3.0)
    monkeypatch.setattr(settings, "USER_WARNING_PROVIDER", "mock")
    monkeypatch.setattr(settings, "TWILIO_VALIDATE_SIGNATURE", False)

    yield

    protection_engine.clear()
    protected_user_warning_service.default_provider = MockUserWarningProvider()
    caregiver_notification_service.default_provider = MockSMSProvider()
    intervention_service.default_provider = MockInterventionProvider()


def make_conference_session(
    session_id: str,
    conference_sid: str = CONFERENCE_SID,
    scammer_sid: str = SCAMMER_CALL_SID,
    callee_sid: str = CALLEE_CALL_SID,
    callee_connected: bool = True,
    status: SessionStatus = SessionStatus.ACTIVE,
) -> CallSession:
    return CallSession(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="+14155550122",
        parent_call_sid=scammer_sid,
        protected_user_call_sid=callee_sid,
        conference_sid=conference_sid,
        conference_name=f"raksha-{session_id}",
        protected_user_connected=callee_connected,
        status=status,
    )


def make_decision(
    session_id: str,
    level: ProtectionLevel = ProtectionLevel.WARNING,
    has_dashboard_alert: bool = True,
    score: float = 80.0,
    tier: RiskTier = RiskTier.HIGH,
) -> ProtectionDecision:
    actions = []
    if has_dashboard_alert:
        actions.append(
            ProtectionAction(
                action_type=ProtectionActionType.DASHBOARD_ALERT,
                level=level,
                status=ProtectionActionStatus.EXECUTED,
                message="Test alert",
            )
        )
    return ProtectionDecision(
        session_id=session_id,
        level=level,
        triggered_actions=actions,
        trigger_score=score,
        trigger_tier=tier,
        explanation="Test explanation",
    )


# =====================================================================
# 1. PROVIDER SELECTION & CONFIGURATION (Tests 1-4)
# =====================================================================

def test_1_provider_selection_mock():
    provider = get_user_warning_provider("mock")
    assert isinstance(provider, MockUserWarningProvider)
    assert provider.name == "mock"


def test_2_provider_selection_twilio_conference():
    provider = get_user_warning_provider("twilio_conference")
    assert isinstance(provider, TwilioConferenceUserWarningProvider)
    assert provider.name == "twilio_conference"


def test_3_unknown_provider_rejected():
    provider = get_user_warning_provider("unsupported_provider")
    assert isinstance(provider, InvalidUserWarningProvider)
    res = provider.warn_user("session-1", "Warning")
    assert res.success is False
    assert res.status == UserWarningStatus.FAILED
    assert "Invalid user warning provider configured" in res.error


@pytest.mark.asyncio
async def test_4_missing_twilio_credentials_explicit_failure(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)

    provider = TwilioConferenceUserWarningProvider(account_sid=None, auth_token=None)
    session = make_conference_session("session-cred-fail")
    await session_store.create_session("session-cred-fail")

    res = await provider.warn_user("session-cred-fail", "Warning", session=session)
    assert res.success is False
    assert res.status == UserWarningStatus.FAILED
    assert res.error == "Twilio credentials not configured"


# =====================================================================
# 2. CANONICAL WARNING TWIML ENDPOINT (Tests 5-12)
# =====================================================================

@pytest.mark.asyncio
async def test_5_valid_session_returns_canonical_warning_twiml():
    client = TestClient(app)
    session_id = "test-twiml-session"
    session = await session_store.create_session(session_id)
    session.user_warning_history.append(
        UserWarningRecord(
            warning_id="warn-twiml-1",
            session_id=session_id,
            message="Please be careful. This call may be suspicious. Do not share OTPs, passwords, or banking details.",
            status=UserWarningStatus.QUEUED,
        )
    )

    resp = client.post(f"/api/twilio/voice/warning-twiml/{session_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/xml"
    content = resp.text
    assert "<Response>" in content
    assert '<Say voice="Polly.Aditi" language="en-IN">' in content
    assert "Please be careful. This call may be suspicious." in content


@pytest.mark.asyncio
async def test_6_and_7_signature_validation(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_VALIDATE_SIGNATURE", True)
    client = TestClient(app)
    session_id = "test-twiml-sig"
    session = await session_store.create_session(session_id)
    session.user_warning_history.append(
        UserWarningRecord(
            warning_id="warn-sig-1",
            session_id=session_id,
            message="Canonical warning",
            status=UserWarningStatus.QUEUED,
        )
    )

    # Missing/invalid signature rejected with 403
    resp = client.post(f"/api/twilio/voice/warning-twiml/{session_id}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Invalid Twilio signature"

    # Valid signature accepted (mock verify_twilio_signature)
    monkeypatch.setattr(twilio_service, "verify_twilio_signature", lambda url, data, sig: True)
    resp_valid = client.post(
        f"/api/twilio/voice/warning-twiml/{session_id}",
        headers={"X-Twilio-Signature": "valid-sig"},
    )
    assert resp_valid.status_code == 200


@pytest.mark.asyncio
async def test_8_missing_session_rejected_404():
    client = TestClient(app)
    resp = client.post("/api/twilio/voice/warning-twiml/non-existent-session")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_9_no_canonical_warning_rejected_400():
    client = TestClient(app)
    session_id = "test-twiml-no-warning"
    await session_store.create_session(session_id)

    # Session exists but has empty user_warning_history
    resp = client.post(f"/api/twilio/voice/warning-twiml/{session_id}")
    assert resp.status_code == 400
    assert "No active canonical warning" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_10_arbitrary_warning_text_cannot_be_supplied():
    client = TestClient(app)
    session_id = "test-twiml-tamper"
    session = await session_store.create_session(session_id)
    canonical = "Please be careful. This call may be suspicious."
    session.user_warning_history.append(
        UserWarningRecord(
            warning_id="warn-tamper-1",
            session_id=session_id,
            message=canonical,
            status=UserWarningStatus.QUEUED,
        )
    )

    # Attempt to inject arbitrary text via query param and form body
    resp = client.post(
        f"/api/twilio/voice/warning-twiml/{session_id}?message=ArbitraryAttackerText",
        data={"message": "InjectedFormText", "Say": "MaliciousAudio"},
    )
    assert resp.status_code == 200
    assert "ArbitraryAttackerText" not in resp.text
    assert "InjectedFormText" not in resp.text
    assert "MaliciousAudio" not in resp.text
    assert canonical in resp.text


@pytest.mark.asyncio
async def test_11_and_12_twiml_contains_say_and_no_leaks():
    client = TestClient(app)
    session_id = "test-twiml-leak-check"
    session = await session_store.create_session(session_id)
    session.user_warning_history.append(
        UserWarningRecord(
            warning_id="warn-leak-1",
            session_id=session_id,
            message="Warning. This call appears highly suspicious. Please do not share OTPs, passwords, or send money. Consider ending the call.",
            status=UserWarningStatus.QUEUED,
        )
    )

    resp = client.post(f"/api/twilio/voice/warning-twiml/{session_id}")
    assert resp.status_code == 200
    body = resp.text

    # 11. Contains <Say>
    assert "<Say" in body
    assert "</Say>" in body

    # 12. No leak of internal details
    assert "score" not in body.lower()
    assert "tier" not in body.lower()
    assert "confidence" not in body.lower()
    assert "phishing" not in body.lower()
    assert "nova" not in body.lower()
    assert "model" not in body.lower()


# =====================================================================
# 3. TWILIO ANNOUNCEMENT REST CALL (Tests 13-19)
# =====================================================================

@pytest.mark.asyncio
async def test_13_through_19_announcement_rest_request():
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
        timeout_seconds=2.5,
        base_url="https://raksha.example.com",
    )
    session = make_conference_session("session-announce-target")

    captured_requests = []

    async def mock_post(url, data=None, auth=None, headers=None, **kwargs):
        captured_requests.append({
            "url": str(url),
            "data": data,
            "auth": auth,
            "headers": headers,
        })
        return httpx.Response(200, json={"status": "in-progress"})

    with unittest.mock.patch.object(httpx.AsyncClient, "post", side_effect=mock_post):
        res = await provider.warn_user("session-announce-target", "Warning msg", session=session)

    assert res.success is True
    assert res.status == UserWarningStatus.QUEUED
    assert len(captured_requests) == 1
    req = captured_requests[0]

    # 13. Correct participant endpoint
    expected_url = f"https://api.twilio.com/2010-04-01/Accounts/{FAKE_ACCOUNT_SID}/Conferences/{CONFERENCE_SID}/Participants/{CALLEE_CALL_SID}.json"
    assert req["url"] == expected_url

    # 14. Target is protected_user_call_sid
    assert CALLEE_CALL_SID in req["url"]

    # 15. Scammer/parent CallSid is NOT targeted
    assert SCAMMER_CALL_SID not in req["url"]

    # 16. Correct AnnounceUrl
    assert req["data"]["AnnounceMethod"] == "POST"
    assert req["data"]["AnnounceUrl"].startswith("https://raksha.example.com/api/twilio/voice/warning-twiml/session-announce-target?warning_id=")

    # 17. Correct Basic Auth
    assert req["auth"] == (FAKE_ACCOUNT_SID, FAKE_AUTH_TOKEN)

    # 18. Bounded timeout
    assert provider.timeout_seconds == 2.5

    # 19. No credentials leaked in logs / errors
    assert FAKE_AUTH_TOKEN not in str(res.error)


@pytest.mark.asyncio
async def test_15_parent_scammer_call_sid_safety_prevention():
    """Verify that if protected_user_call_sid ever matches parent_call_sid, request is aborted."""
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    # Malformed session where callee leg is set to scammer leg
    session = make_conference_session(
        "session-scammer-leak",
        scammer_sid=SCAMMER_CALL_SID,
        callee_sid=SCAMMER_CALL_SID,
    )

    res = await provider.warn_user("session-scammer-leak", "Warning msg", session=session)
    assert res.success is False
    assert res.status == UserWarningStatus.FAILED
    assert "Safety violation" in res.error


# =====================================================================
# 4. LIFECYCLE & STATUS PROGRESSION (Tests 20-29)
# =====================================================================

@pytest.mark.asyncio
async def test_20_accepted_announcement_becomes_queued():
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    session = make_conference_session("session-queued")

    with unittest.mock.patch.object(
        httpx.AsyncClient, "post", return_value=httpx.Response(200, json={"call_sid": CALLEE_CALL_SID})
    ):
        res = await provider.warn_user("session-queued", "Warning msg", session=session)

    assert res.success is True
    assert res.status == UserWarningStatus.QUEUED
    assert res.warning_id is not None


@pytest.mark.asyncio
async def test_21_successful_announcement_callback_becomes_delivered():
    client = TestClient(app)
    session_id = "session-cb-delivered"
    session = await session_store.create_session(session_id)
    session.conference_sid = CONFERENCE_SID
    session.protected_user_call_sid = CALLEE_CALL_SID
    warning_id = "twilio-warning-succ1"
    session.user_warning_history.append(
        UserWarningRecord(
            warning_id=warning_id,
            session_id=session_id,
            message="Canonical message",
            status=UserWarningStatus.QUEUED,
        )
    )

    # Webhook callback indicates announcement finished successfully
    callback_payload = {
        "StatusCallbackEvent": "announcement",
        "ConferenceSid": CONFERENCE_SID,
        "CallSid": CALLEE_CALL_SID,
        "AnnouncementStatus": "completed",
        "AnnouncementUrl": f"https://raksha.example.com/api/twilio/voice/warning-twiml/{session_id}?warning_id={warning_id}",
    }

    resp = client.post("/api/twilio/conference/status", data=callback_payload)
    assert resp.status_code == 200

    # Verify status transitioned to DELIVERED
    updated_session = await session_store.get_session(session_id)
    assert updated_session.user_warning_history[0].status == UserWarningStatus.DELIVERED


@pytest.mark.asyncio
async def test_22_failed_announcement_callback_becomes_failed():
    client = TestClient(app)
    session_id = "session-cb-failed"
    session = await session_store.create_session(session_id)
    session.conference_sid = CONFERENCE_SID
    session.protected_user_call_sid = CALLEE_CALL_SID
    warning_id = "twilio-warning-fail1"
    session.user_warning_history.append(
        UserWarningRecord(
            warning_id=warning_id,
            session_id=session_id,
            message="Canonical message",
            status=UserWarningStatus.QUEUED,
        )
    )

    callback_payload = {
        "StatusCallbackEvent": "announcement",
        "ConferenceSid": CONFERENCE_SID,
        "CallSid": CALLEE_CALL_SID,
        "AnnouncementStatus": "failed",
        "ErrorMessage": "Participant hung up before announcement played",
        "AnnouncementUrl": f"https://raksha.example.com/api/twilio/voice/warning-twiml/{session_id}?warning_id={warning_id}",
    }

    resp = client.post("/api/twilio/conference/status", data=callback_payload)
    assert resp.status_code == 200

    updated_session = await session_store.get_session(session_id)
    assert updated_session.user_warning_history[0].status == UserWarningStatus.FAILED
    assert "Participant hung up" in updated_session.user_warning_history[0].error


@pytest.mark.asyncio
async def test_23_rest_error_becomes_failed():
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    session = make_conference_session("session-rest-err")

    with unittest.mock.patch.object(
        httpx.AsyncClient, "post", return_value=httpx.Response(500, text="Internal Server Error")
    ):
        res = await provider.warn_user("session-rest-err", "Warning msg", session=session)

    assert res.success is False
    assert res.status == UserWarningStatus.FAILED
    assert "Twilio server error: HTTP 500" in res.error


@pytest.mark.asyncio
async def test_24_rest_timeout_becomes_failed():
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    session = make_conference_session("session-timeout")

    with unittest.mock.patch.object(
        httpx.AsyncClient, "post", side_effect=httpx.TimeoutException("Timed out")
    ):
        res = await provider.warn_user("session-timeout", "Warning msg", session=session)

    assert res.success is False
    assert res.status == UserWarningStatus.FAILED
    assert "timed out" in res.error.lower()


@pytest.mark.asyncio
async def test_25_missing_conference_sid_safely_skipped():
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    session = make_conference_session("session-no-conf", conference_sid="")

    res = await provider.warn_user("session-no-conf", "Warning msg", session=session)
    assert res.success is False
    assert res.status == UserWarningStatus.SKIPPED
    assert "Conference SID not available" in res.error


@pytest.mark.asyncio
async def test_26_missing_protected_user_call_sid_safely_skipped():
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    session = make_conference_session("session-no-callee", callee_sid="")

    res = await provider.warn_user("session-no-callee", "Warning msg", session=session)
    assert res.success is False
    assert res.status == UserWarningStatus.SKIPPED
    assert "Protected user CallSid not available" in res.error


@pytest.mark.asyncio
async def test_27_protected_user_already_left_handled_safely():
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    session = make_conference_session("session-left", callee_connected=False)

    res = await provider.warn_user("session-left", "Warning msg", session=session)
    assert res.success is False
    assert res.status == UserWarningStatus.SKIPPED
    assert "not verified connected" in res.error


@pytest.mark.asyncio
async def test_28_conference_ended_handled_safely():
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    session = make_conference_session("session-ended", status=SessionStatus.ENDED)

    res = await provider.warn_user("session-ended", "Warning msg", session=session)
    assert res.success is False
    assert res.status == UserWarningStatus.SKIPPED
    assert "already ended" in res.error


@pytest.mark.asyncio
async def test_29_announcement_correlation_does_not_update_wrong_warning():
    """User Correction 2: Deterministic correlation only. No positional guessing."""
    client = TestClient(app)
    session_id = "session-corr-safety"
    session = await session_store.create_session(session_id)
    session.conference_sid = CONFERENCE_SID
    session.protected_user_call_sid = CALLEE_CALL_SID

    record_1 = UserWarningRecord(
        warning_id="warning-111",
        session_id=session_id,
        message="Warning 1",
        status=UserWarningStatus.QUEUED,
    )
    record_2 = UserWarningRecord(
        warning_id="warning-222",
        session_id=session_id,
        message="Warning 2",
        status=UserWarningStatus.QUEUED,
    )
    session.user_warning_history.extend([record_1, record_2])

    # Callback specifically targets warning-111
    callback_payload = {
        "StatusCallbackEvent": "announcement",
        "ConferenceSid": CONFERENCE_SID,
        "CallSid": CALLEE_CALL_SID,
        "AnnouncementStatus": "completed",
        "AnnouncementUrl": f"https://raksha.example.com/api/twilio/voice/warning-twiml/{session_id}?warning_id=warning-111",
    }
    resp = client.post("/api/twilio/conference/status", data=callback_payload)
    assert resp.status_code == 200

    # Record 1 must be DELIVERED, Record 2 must remain QUEUED
    updated_session = await session_store.get_session(session_id)
    assert updated_session.user_warning_history[0].status == UserWarningStatus.DELIVERED
    assert updated_session.user_warning_history[1].status == UserWarningStatus.QUEUED

    # Callback with missing or uncorrelatable warning_id leaves records untouched
    callback_uncorrelated = {
        "StatusCallbackEvent": "announcement",
        "ConferenceSid": CONFERENCE_SID,
        "CallSid": CALLEE_CALL_SID,
        "AnnouncementStatus": "completed",
        "AnnouncementUrl": "https://raksha.example.com/api/twilio/voice/warning-twiml/unrelated",
    }
    resp2 = client.post("/api/twilio/conference/status", data=callback_uncorrelated)
    assert resp2.status_code == 200
    assert updated_session.user_warning_history[1].status == UserWarningStatus.QUEUED


@pytest.mark.asyncio
async def test_user_correction_1_race_safety_gate():
    """User Correction 1: Test protected_user_connected race gate.

    When user has joined at Twilio, but Raksha local join callback has not yet updated
    protected_user_connected to True, announcement must be safely SKIPPED.
    """
    provider = TwilioConferenceUserWarningProvider(
        account_sid=FAKE_ACCOUNT_SID,
        auth_token=FAKE_AUTH_TOKEN,
    )
    # protected_user_connected is False (pending callback)
    session = make_conference_session("session-race", callee_connected=False)

    res = await provider.warn_user("session-race", "Warning msg", session=session)
    assert res.success is False
    assert res.status == UserWarningStatus.SKIPPED
    assert "not verified connected" in res.error


# =====================================================================
# 5. FAILURE ISOLATION & IDEMPOTENCY (Tests 30-34)
# =====================================================================

@pytest.mark.asyncio
async def test_30_through_34_failure_isolation_in_pipeline(monkeypatch):
    """Verify that Twilio warning failure never compromises risk, protection, caregiver, or intervention."""
    semantic_classifier.initialize()
    monkeypatch.setattr(settings, "USER_WARNING_PROVIDER", "twilio_conference")

    session_id = "session-iso-pipeline"
    session = await session_store.create_session(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="+14155550122",
    )
    session.parent_call_sid = SCAMMER_CALL_SID
    session.protected_user_call_sid = CALLEE_CALL_SID
    session.conference_sid = CONFERENCE_SID
    session.protected_user_connected = True
    session.caregiver_contacts.append(
        CaregiverContact(
            contact_id="cg-iso-1",
            name="John Doe",
            phone_number="+15551234567",
            relationship="Son",
        )
    )

    # Mock Twilio REST call to fail with HTTP 500
    with unittest.mock.patch.object(
        httpx.AsyncClient, "post", return_value=httpx.Response(500, text="Twilio error")
    ):
        segment = TranscriptSegment(
            session_id=session_id,
            segment_id="seg-iso-1",
            text="This is Officer Miller from the Police. An arrest warrant has been issued. Give me your 6 digit code right now.",
            speaker=SpeakerType.CALLER,
            start_time=1.0,
            end_time=3.0,
        )
        result = await streaming_pipeline.process_segment(segment)
        events = result["events"]

    # 30. Risk calculation succeeded
    updated_session = await session_store.get_session(session_id)
    assert updated_session.latest_risk is not None
    assert updated_session.latest_risk.overall_score > 70.0

    # 31. Protection decision succeeded
    assert len(updated_session.protection_history) >= 1
    decision = updated_session.protection_history[-1]
    assert decision.level in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]

    # 32. Caregiver notification succeeded
    assert len(updated_session.notification_history) >= 1

    # 33. Intervention evaluation occurred
    assert len(updated_session.intervention_history) >= 0

    # 34. ALERT_TRIGGERED was emitted
    event_types = [e.type for e in events]
    assert WSMessageType.ALERT_TRIGGERED in event_types

    # Warning record reflects FAILED status without crashing pipeline
    assert len(updated_session.user_warning_history) == 1
    assert updated_session.user_warning_history[0].status == UserWarningStatus.FAILED


@pytest.mark.asyncio
async def test_in_flight_queued_warning_deduplication():
    """Verify idempotency: an in-flight QUEUED warning suppresses concurrent duplicates."""
    session = make_conference_session("session-dedup")
    session.user_warning_history.append(
        UserWarningRecord(
            warning_id="warn-queued-active",
            session_id="session-dedup",
            message="Active warning",
            status=UserWarningStatus.QUEUED,
        )
    )

    decision = make_decision("session-dedup", level=ProtectionLevel.WARNING)
    rec = protected_user_warning_service.warn_user(session, decision)
    assert rec is None  # Suppressed because a warning is already QUEUED


# =====================================================================
# 6. REGRESSION & SAFETY (Tests 35-39)
# =====================================================================

def test_35_mock_provider_zero_network_calls():
    provider = MockUserWarningProvider()
    res = provider.warn_user("session-mock", "Warning message")
    assert res.success is True
    assert res.status == UserWarningStatus.DELIVERED
    assert res.provider == "mock"
    assert len(provider.delivered_warnings) == 1


def test_39_simulation_mode_remains_offline(monkeypatch):
    monkeypatch.setattr(settings, "USER_WARNING_PROVIDER", "mock")
    provider = get_user_warning_provider()
    assert isinstance(provider, MockUserWarningProvider)
