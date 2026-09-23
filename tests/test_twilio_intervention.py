import asyncio
import logging
import re
import unittest.mock
import pytest
from fastapi.testclient import TestClient
import httpx

from backend.app.config import settings
from backend.app.main import app
from backend.app.models import (
    CallSession,
    CaregiverContact,
    InterventionRecord,
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
    SpeakerType,
    TacticMatch,
    TranscriptSegment,
    UserWarningStatus,
    WSMessageType,
)
from backend.app.services.intervention_service import (
    BaseInterventionProvider,
    InterventionService,
    InvalidInterventionProvider,
    MockInterventionProvider,
    TwilioRESTInterventionProvider,
    get_intervention_provider,
    intervention_service,
)
from backend.app.services.notification_service import (
    MockSMSProvider,
    caregiver_notification_service,
)
from backend.app.services.user_warning_service import (
    MockUserWarningProvider,
    protected_user_warning_service,
)
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.protection_engine import protection_engine
from backend.app.services.session_store import session_store
from ai.classifier import semantic_classifier

# Synthetic test credentials (NEVER real credentials)
FAKE_ACCOUNT_SID = "TEST_ACCOUNT_SID"
FAKE_AUTH_TOKEN = "TEST_AUTH_TOKEN"
VALID_CALL_SID = "CA11112222333344445555666677778888"
VALID_CALL_SID_2 = "CA99998888777766665555444433332222"


@pytest.fixture(autouse=True)
def reset_intervention_state(monkeypatch):
    """Reset global settings and services before and after each test."""
    protection_engine.clear()
    intervention_service.default_provider = None
    caregiver_notification_service.default_provider = MockSMSProvider()
    protected_user_warning_service.default_provider = MockUserWarningProvider()

    # Configure fake Twilio credentials and mock provider by default
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", FAKE_ACCOUNT_SID)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", FAKE_AUTH_TOKEN)
    monkeypatch.setattr(settings, "TWILIO_API_TIMEOUT_SECONDS", 3.0)
    monkeypatch.setattr(settings, "INTERVENTION_PROVIDER", "mock")

    yield

    protection_engine.clear()
    intervention_service.default_provider = MockInterventionProvider()
    caregiver_notification_service.default_provider = MockSMSProvider()
    protected_user_warning_service.default_provider = MockUserWarningProvider()


def make_test_session(session_id: str) -> CallSession:
    return CallSession(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="Margaret H.",
    )


def make_decision(
    session_id: str,
    level: ProtectionLevel,
    has_dashboard_alert: bool = True,
    score: float = 95.0,
    tier: RiskTier = RiskTier.CRITICAL,
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


def make_risk_with_tactic(
    session_id: str,
    tactic: ManipulationCategory,
    score: float = 95.0,
    tier: RiskTier = RiskTier.CRITICAL,
) -> RiskAssessment:
    return RiskAssessment(
        session_id=session_id,
        overall_score=score,
        risk_tier=tier,
        triggered_tactics=[
            TacticMatch(
                tactic=tactic,
                confidence=0.95,
                evidence_text="Test trigger phrase",
                explanation="Test explanation",
            )
        ],
        explanation="Test risk assessment",
    )


# --- 1. Valid Twilio CallSid + successful disconnect ---
@pytest.mark.asyncio
async def test_valid_twilio_callsid_successful_disconnect():
    mock_resp = httpx.Response(
        200,
        json={"sid": VALID_CALL_SID, "status": "completed"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        assert result.success is True
        assert result.provider == "twilio"
        assert result.status == InterventionStatus.EXECUTED
        assert result.intervention_id == VALID_CALL_SID
        assert result.error is None

        # Verify exact HTTP request details
        assert mock_post.call_count == 1
        called_url = mock_post.call_args[0][0]
        called_kwargs = mock_post.call_args[1]

        expected_url = f"https://api.twilio.com/2010-04-01/Accounts/{FAKE_ACCOUNT_SID}/Calls/{VALID_CALL_SID}.json"
        assert called_url == expected_url
        assert called_kwargs["data"] == {"Status": "completed"}
        assert called_kwargs["auth"] == (FAKE_ACCOUNT_SID, FAKE_AUTH_TOKEN)


# --- 2. Correct HTTP method and path ---
@pytest.mark.asyncio
async def test_correct_http_method_and_path():
    mock_resp = httpx.Response(
        200,
        json={"sid": VALID_CALL_SID, "status": "completed"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        await provider.disconnect_call(VALID_CALL_SID)

        assert mock_post.call_count == 1
        url = mock_post.call_args[0][0]
        assert f"/2010-04-01/Accounts/{FAKE_ACCOUNT_SID}/Calls/{VALID_CALL_SID}.json" in url


# --- 3. 404 / already-ended call ---
@pytest.mark.asyncio
async def test_404_already_ended_call():
    mock_resp = httpx.Response(
        404,
        json={"code": 20404, "message": "The requested resource was not found"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        assert result.success is False
        assert result.provider == "twilio"
        assert result.status == InterventionStatus.SKIPPED
        assert "404" in result.error


# --- 4. 400 Twilio rejection (not in-progress vs generic rejection) ---
@pytest.mark.asyncio
async def test_400_twilio_rejection():
    # 4a: Code 21220 ("Call is not in-progress") -> SKIPPED
    mock_resp_21220 = httpx.Response(
        400,
        json={"code": 21220, "message": "Call is not in-progress"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    with unittest.mock.patch.object(
        httpx.AsyncClient, "post", unittest.mock.AsyncMock(return_value=mock_resp_21220)
    ):
        provider = TwilioRESTInterventionProvider()
        res_skipped = await provider.disconnect_call(VALID_CALL_SID)
        assert res_skipped.success is False
        assert res_skipped.status == InterventionStatus.SKIPPED

    # 4b: Generic 400 rejection -> FAILED
    mock_resp_generic = httpx.Response(
        400,
        json={"code": 21601, "message": "Invalid Parameter"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    with unittest.mock.patch.object(
        httpx.AsyncClient, "post", unittest.mock.AsyncMock(return_value=mock_resp_generic)
    ):
        provider = TwilioRESTInterventionProvider()
        res_failed = await provider.disconnect_call(VALID_CALL_SID)
        assert res_failed.success is False
        assert res_failed.status == InterventionStatus.FAILED
        assert "400" in res_failed.error


# --- 5. 401 authentication failure & secret sanitization ---
@pytest.mark.asyncio
async def test_401_authentication_failure():
    mock_resp = httpx.Response(
        401,
        json={"code": 20003, "message": "Authentication Error - invalid credentials"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        assert result.success is False
        assert result.status == InterventionStatus.FAILED
        assert result.provider == "twilio"
        # Secret sanitization check: auth token must NEVER appear in error message
        assert FAKE_AUTH_TOKEN not in result.error
        assert "401" in result.error


# --- 6. 403 authorization failure ---
@pytest.mark.asyncio
async def test_403_authorization_failure():
    mock_resp = httpx.Response(
        403,
        json={"code": 20008, "message": "Forbidden"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        assert result.success is False
        assert result.status == InterventionStatus.FAILED
        assert "403" in result.error


# --- 7. 500 Twilio server failure ---
@pytest.mark.asyncio
async def test_500_twilio_server_failure():
    mock_resp = httpx.Response(
        500,
        text="Internal Server Error",
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        assert result.success is False
        assert result.status == InterventionStatus.FAILED
        assert "500" in result.error


# --- 8. Timeout failure ---
@pytest.mark.asyncio
async def test_timeout_failure():
    mock_post = unittest.mock.AsyncMock(
        side_effect=httpx.TimeoutException("Connection timed out after 3.0s")
    )

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        assert result.success is False
        assert result.status == InterventionStatus.FAILED
        assert "timed out" in result.error.lower()


# --- 9. Network failure ---
@pytest.mark.asyncio
async def test_network_failure():
    mock_post = unittest.mock.AsyncMock(
        side_effect=httpx.NetworkError("Failed to resolve api.twilio.com")
    )

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        assert result.success is False
        assert result.status == InterventionStatus.FAILED
        assert "network connection failed" in result.error.lower()


# --- 10. Invalid CallSid (e.g. test-session-123) ---
@pytest.mark.asyncio
async def test_invalid_callsid_rejected_no_http():
    mock_post = unittest.mock.AsyncMock()

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call("test-session-123")

        # Provider must NOT make an HTTP request
        assert mock_post.call_count == 0
        assert result.success is False
        assert result.status == InterventionStatus.SKIPPED
        assert "Invalid Twilio CallSid format" in result.error


# --- 11. Malformed CallSids rejected without HTTP calls ---
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_sid",
    [
        "CA123",
        "CAZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",
        "CA1111222233334444555566667777888",  # 33 chars (1 short)
        "CA111122223333444455556666777788889",  # 35 chars (1 long)
        "CB11112222333344445555666677778888",  # Wrong prefix
        "",
        "None",
    ],
)
async def test_malformed_callsid_rejected_no_http(malformed_sid):
    mock_post = unittest.mock.AsyncMock()

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(malformed_sid)

        assert mock_post.call_count == 0
        assert result.success is False
        assert result.status == InterventionStatus.SKIPPED


# --- 12. Simulation sessions cannot invoke Twilio provider ---
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sim_id",
    [
        "test-sim-call-123",
        "simulation-session-456",
        "mock-session-789",
    ],
)
async def test_simulation_session_cannot_invoke_twilio(sim_id):
    mock_post = unittest.mock.AsyncMock()

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(sim_id)

        assert mock_post.call_count == 0
        assert result.success is False
        assert result.status == InterventionStatus.SKIPPED


# --- 13. Mock mode continues to use MockInterventionProvider ---
def test_mock_mode_provider_selection(monkeypatch):
    monkeypatch.setattr(settings, "INTERVENTION_PROVIDER", "mock")
    prov = get_intervention_provider()
    assert isinstance(prov, MockInterventionProvider)
    assert prov.name == "mock"


# --- 14. Explicit Twilio mode with missing credentials ---
@pytest.mark.asyncio
async def test_explicit_twilio_mode_missing_credentials(monkeypatch):
    monkeypatch.setattr(settings, "INTERVENTION_PROVIDER", "twilio")
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)

    mock_post = unittest.mock.AsyncMock()
    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        # Zero HTTP calls, no mock fallback, safe FAILED result
        assert mock_post.call_count == 0
        assert result.success is False
        assert result.status == InterventionStatus.FAILED
        assert "credentials not configured" in result.error.lower()


# --- 15. Invalid provider configuration fails safely ---
def test_invalid_provider_configuration(monkeypatch):
    monkeypatch.setattr(settings, "INTERVENTION_PROVIDER", "unsupported_carrier")
    prov = get_intervention_provider()
    assert isinstance(prov, InvalidInterventionProvider)
    assert not isinstance(prov, MockInterventionProvider)

    res = prov.disconnect_call(VALID_CALL_SID)
    assert res.success is False
    assert res.status == InterventionStatus.FAILED
    assert "Invalid intervention provider" in res.error


# --- 16. Duplicate intervention produces only ONE HTTP request ---
@pytest.mark.asyncio
async def test_duplicate_intervention_only_one_http():
    mock_resp = httpx.Response(
        200,
        json={"sid": VALID_CALL_SID, "status": "completed"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        service = InterventionService(default_provider=provider)

        session = make_test_session(VALID_CALL_SID)
        decision = make_decision(VALID_CALL_SID, level=ProtectionLevel.CRITICAL_INTERCEPT)
        risk = make_risk_with_tactic(VALID_CALL_SID, ManipulationCategory.INFORMATION_PHISHING)

        # First evaluation: dispatches HTTP POST
        rec1 = await service.evaluate_and_execute(session, decision, risk)
        assert rec1 is not None
        assert rec1.status == InterventionStatus.EXECUTED
        assert mock_post.call_count == 1

        # Second evaluation: suppressed under idempotency invariant
        rec2 = await service.evaluate_and_execute(session, decision, risk)
        assert rec2 is not None
        assert rec2.status == InterventionStatus.SUPPRESSED

        # Still exactly ONE HTTP request
        assert mock_post.call_count == 1


# --- 17. Concurrent duplicate intervention produces only ONE HTTP request ---
@pytest.mark.asyncio
async def test_concurrent_duplicate_intervention():
    async def delayed_post(*args, **kwargs):
        await asyncio.sleep(0.05)
        return httpx.Response(
            200,
            json={"sid": VALID_CALL_SID, "status": "completed"},
            request=httpx.Request("POST", "https://api.twilio.com"),
        )

    mock_post = unittest.mock.AsyncMock(side_effect=delayed_post)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        service = InterventionService(default_provider=provider)

        session = make_test_session(VALID_CALL_SID)
        decision = make_decision(VALID_CALL_SID, level=ProtectionLevel.CRITICAL_INTERCEPT)
        risk = make_risk_with_tactic(VALID_CALL_SID, ManipulationCategory.INFORMATION_PHISHING)

        # Launch 3 concurrent requests
        results = await asyncio.gather(
            service.evaluate_and_execute(session, decision, risk),
            service.evaluate_and_execute(session, decision, risk),
            service.evaluate_and_execute(session, decision, risk),
        )

        statuses = [r.status for r in results if r]
        assert statuses.count(InterventionStatus.EXECUTED) == 1
        assert statuses.count(InterventionStatus.SUPPRESSED) == 2
        # Exactly one outbound HTTP request
        assert mock_post.call_count == 1


# --- 18. HIGH tier does NOT trigger HTTP disconnect ---
@pytest.mark.asyncio
async def test_high_tier_does_not_trigger_http():
    mock_post = unittest.mock.AsyncMock()

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        service = InterventionService(default_provider=provider)

        session = make_test_session(VALID_CALL_SID)
        decision = make_decision(
            VALID_CALL_SID,
            level=ProtectionLevel.WARNING,
            score=85.0,
            tier=RiskTier.HIGH,
        )
        risk = make_risk_with_tactic(
            VALID_CALL_SID,
            ManipulationCategory.INFORMATION_PHISHING,
            score=85.0,
            tier=RiskTier.HIGH,
        )

        rec = await service.evaluate_and_execute(session, decision, risk)
        assert rec is None
        assert mock_post.call_count == 0


# --- 19. CRITICAL without acute tactic produces no HTTP request ---
@pytest.mark.asyncio
async def test_critical_without_acute_tactic_no_http():
    mock_post = unittest.mock.AsyncMock()

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        service = InterventionService(default_provider=provider)

        session = make_test_session(VALID_CALL_SID)
        decision = make_decision(VALID_CALL_SID, level=ProtectionLevel.CRITICAL_INTERCEPT)
        # URGENCY is not an acute extraction tactic
        risk = make_risk_with_tactic(VALID_CALL_SID, ManipulationCategory.URGENCY)

        rec = await service.evaluate_and_execute(session, decision, risk)
        assert rec is None
        assert mock_post.call_count == 0


# --- 20. Cooldown-suppressed CRITICAL produces no HTTP request ---
@pytest.mark.asyncio
async def test_cooldown_suppressed_critical_no_http():
    mock_post = unittest.mock.AsyncMock()

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        service = InterventionService(default_provider=provider)

        session = make_test_session(VALID_CALL_SID)
        # Suppressed dashboard alert -> has_dashboard_alert is False
        decision = make_decision(
            VALID_CALL_SID,
            level=ProtectionLevel.CRITICAL_INTERCEPT,
            has_dashboard_alert=False,
        )
        risk = make_risk_with_tactic(VALID_CALL_SID, ManipulationCategory.INFORMATION_PHISHING)

        rec = await service.evaluate_and_execute(session, decision, risk)
        assert rec is None
        assert mock_post.call_count == 0


# --- 21. CRITICAL + INFORMATION_PHISHING triggers exactly one HTTP request ---
@pytest.mark.asyncio
async def test_critical_with_information_phishing_triggers_one_http():
    mock_resp = httpx.Response(
        200,
        json={"sid": VALID_CALL_SID, "status": "completed"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        service = InterventionService(default_provider=provider)

        session = make_test_session(VALID_CALL_SID)
        decision = make_decision(VALID_CALL_SID, level=ProtectionLevel.CRITICAL_INTERCEPT)
        risk = make_risk_with_tactic(VALID_CALL_SID, ManipulationCategory.INFORMATION_PHISHING)

        rec = await service.evaluate_and_execute(session, decision, risk)
        assert rec is not None
        assert rec.status == InterventionStatus.EXECUTED
        assert mock_post.call_count == 1


# --- 22. CRITICAL + FINANCIAL_REDIRECTION triggers exactly one HTTP request ---
@pytest.mark.asyncio
async def test_critical_with_financial_redirection_triggers_one_http():
    mock_resp = httpx.Response(
        200,
        json={"sid": VALID_CALL_SID, "status": "completed"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        service = InterventionService(default_provider=provider)

        session = make_test_session(VALID_CALL_SID)
        decision = make_decision(VALID_CALL_SID, level=ProtectionLevel.CRITICAL_INTERCEPT)
        risk = make_risk_with_tactic(VALID_CALL_SID, ManipulationCategory.FINANCIAL_REDIRECTION)

        rec = await service.evaluate_and_execute(session, decision, risk)
        assert rec is not None
        assert rec.status == InterventionStatus.EXECUTED
        assert mock_post.call_count == 1


# --- 23. Session isolation ---
@pytest.mark.asyncio
async def test_session_isolation():
    mock_resp = httpx.Response(
        200,
        json={"sid": VALID_CALL_SID, "status": "completed"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        service = InterventionService(default_provider=provider)

        s1 = make_test_session(VALID_CALL_SID)
        s2 = make_test_session(VALID_CALL_SID_2)

        d1 = make_decision(VALID_CALL_SID, level=ProtectionLevel.CRITICAL_INTERCEPT)
        r1 = make_risk_with_tactic(VALID_CALL_SID, ManipulationCategory.INFORMATION_PHISHING)

        d2 = make_decision(
            VALID_CALL_SID_2,
            level=ProtectionLevel.WARNING,
            score=80.0,
            tier=RiskTier.HIGH,
        )
        r2 = make_risk_with_tactic(
            VALID_CALL_SID_2,
            ManipulationCategory.INFORMATION_PHISHING,
            score=80.0,
            tier=RiskTier.HIGH,
        )

        res1 = await service.evaluate_and_execute(s1, d1, r1)
        res2 = await service.evaluate_and_execute(s2, d2, r2)

        assert res1 is not None
        assert res1.status == InterventionStatus.EXECUTED
        assert res2 is None
        assert mock_post.call_count == 1
        assert len(s1.intervention_history) == 1
        assert len(s2.intervention_history) == 0


# --- 24. Mock regression ---
@pytest.mark.asyncio
async def test_mock_regression():
    provider = MockInterventionProvider()
    service = InterventionService(default_provider=provider)

    session = make_test_session("test-sim-mock")
    decision = make_decision("test-sim-mock", level=ProtectionLevel.CRITICAL_INTERCEPT)
    risk = make_risk_with_tactic("test-sim-mock", ManipulationCategory.INFORMATION_PHISHING)

    rec = await service.evaluate_and_execute(session, decision, risk)
    assert rec is not None
    assert rec.status == InterventionStatus.EXECUTED
    assert rec.provider == "mock"
    assert len(provider.executed_disconnects) == 1


# --- 25. Secret sanitization across failures and logs ---
@pytest.mark.asyncio
async def test_secret_sanitization(caplog):
    caplog.set_level(logging.DEBUG)
    mock_resp = httpx.Response(
        401,
        text=f"Unauthorized: basic auth failed for {FAKE_AUTH_TOKEN}",
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TwilioRESTInterventionProvider()
        result = await provider.disconnect_call(VALID_CALL_SID)

        assert result.status == InterventionStatus.FAILED
        # Verify secret never appears in error field
        assert FAKE_AUTH_TOKEN not in (result.error or "")

        # Verify secret never appears in any captured log message
        for record in caplog.records:
            assert FAKE_AUTH_TOKEN not in record.getMessage()


# --- 26. Harmonious 7A/7B/7C/7D execution ---
@pytest.mark.asyncio
async def test_harmonious_pipeline_execution():
    semantic_classifier.initialize()
    session_id = VALID_CALL_SID
    session = await session_store.create_session(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="Margaret H.",
    )
    session.caregiver_contacts = [
        CaregiverContact(name="Alice Doe", phone_number="+18005550111", enabled=True)
    ]

    mock_resp = httpx.Response(
        200,
        json={"sid": VALID_CALL_SID, "status": "completed"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        # Explicitly configure live Twilio intervention provider for this test
        intervention_service.default_provider = TwilioRESTInterventionProvider()

        segment = TranscriptSegment(
            session_id=session_id,
            speaker=SpeakerType.CALLER,
            text="This is Officer Miller from the Federal Police. An arrest warrant has been issued. Read me the six digit security code right now.",
        )

        result = await streaming_pipeline.process_segment(segment, broadcast=False)

        # 7A: Protection decision
        assert result["protection"] is not None
        assert result["protection"].level in [
            ProtectionLevel.WARNING,
            ProtectionLevel.CRITICAL_INTERCEPT,
        ]

        # 7B: Caregiver notification
        assert len(result["notifications"]) == 1
        assert result["notifications"][0].status.value == "SENT"

        # 7C: Protected user warning
        assert result["user_warning"] is not None
        assert result["user_warning"].status == UserWarningStatus.DELIVERED

        # 7D-2: Twilio REST intervention
        assert result["intervention"] is not None
        assert result["intervention"].status == InterventionStatus.EXECUTED
        assert result["intervention"].provider == "twilio"
        assert mock_post.call_count == 1


# --- 27. WebSocket event ordering preserved ---
def test_ws_event_ordering_preserved(client: TestClient):
    semantic_classifier.initialize()
    session_id = VALID_CALL_SID

    mock_resp = httpx.Response(
        200,
        json={"sid": VALID_CALL_SID, "status": "completed"},
        request=httpx.Request("POST", "https://api.twilio.com"),
    )
    mock_post = unittest.mock.AsyncMock(return_value=mock_resp)

    with unittest.mock.patch.object(httpx.AsyncClient, "post", mock_post):
        intervention_service.default_provider = TwilioRESTInterventionProvider()

        with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
            init_msg = websocket.receive_json()
            assert init_msg["type"] == WSMessageType.SESSION_STATUS.value

            websocket.send_json(
                {
                    "type": WSMessageType.TRANSCRIPT_UPDATE.value,
                    "data": {
                        "speaker": "CALLER",
                        "text": (
                            "This is Officer Miller from the Federal Police. "
                            "An arrest warrant has been issued in your name for criminal money laundering. "
                            "You have only fifteen minutes to resolve this. "
                            "Do not tell your family. Read me the six digit security code right now."
                        ),
                        "is_final": True,
                    },
                }
            )

            # Event 1: TRANSCRIPT_UPDATE
            e1 = websocket.receive_json()
            assert e1["type"] == WSMessageType.TRANSCRIPT_UPDATE.value

            # Event 2: TACTIC_DETECTED
            e2 = websocket.receive_json()
            assert e2["type"] == WSMessageType.TACTIC_DETECTED.value

            # Event 3: RISK_UPDATE
            e3 = websocket.receive_json()
            assert e3["type"] == WSMessageType.RISK_UPDATE.value

            # Event 4: ALERT_TRIGGERED
            e4 = websocket.receive_json()
            assert e4["type"] == WSMessageType.ALERT_TRIGGERED.value
            assert e4["data"]["session_id"] == session_id
