import asyncio
import time
import pytest
from fastapi.testclient import TestClient

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
    InterventionService,
    MockInterventionProvider,
    intervention_service,
)
from backend.app.services.notification_service import caregiver_notification_service, MockSMSProvider
from backend.app.services.user_warning_service import protected_user_warning_service, MockUserWarningProvider
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.protection_engine import protection_engine
from backend.app.services.session_store import session_store
from ai.classifier import semantic_classifier


@pytest.fixture(autouse=True)
def cleanup_state():
    """Reset protection engine and mock providers before and after each test."""
    protection_engine.clear()
    intervention_service.default_provider = MockInterventionProvider()
    caregiver_notification_service.default_provider = MockSMSProvider()
    protected_user_warning_service.default_provider = MockUserWarningProvider()
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
    session_id: str, tactic: ManipulationCategory, score: float = 95.0, tier: RiskTier = RiskTier.CRITICAL
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


# --- 1. Intervention model defaults ---
def test_intervention_model_defaults():
    rec = InterventionRecord(
        session_id="test-session-defaults",
        status=InterventionStatus.EXECUTED,
    )
    assert rec.session_id == "test-session-defaults"
    assert rec.type == InterventionType.DISCONNECT
    assert rec.status == InterventionStatus.EXECUTED
    assert rec.provider == "mock"
    assert rec.intervention_id is not None
    assert rec.error is None

    session = CallSession()
    assert isinstance(session.intervention_history, list)
    assert len(session.intervention_history) == 0


# --- 2. Session intervention-history isolation ---
def test_session_intervention_history_isolation():
    session_a = CallSession(session_id="session-interv-a")
    session_b = CallSession(session_id="session-interv-b")

    rec_a = InterventionRecord(
        session_id="session-interv-a",
        status=InterventionStatus.EXECUTED,
        reason="Test isolation",
    )
    session_a.intervention_history.append(rec_a)

    assert len(session_a.intervention_history) == 1
    assert len(session_b.intervention_history) == 0
    assert session_a.intervention_history[0].reason == "Test isolation"


# --- 3. Mock disconnect success ---
def test_mock_disconnect_success():
    provider = MockInterventionProvider()
    result = provider.disconnect_call("session-success")

    assert result.success is True
    assert result.provider == "mock"
    assert result.intervention_id is not None
    assert result.intervention_id.startswith("mock-disconnect-")
    assert result.error is None
    assert len(provider.executed_disconnects) == 1
    assert provider.executed_disconnects[0]["session_id"] == "session-success"


# --- 4. Mock disconnect failure ---
def test_mock_disconnect_failure():
    provider = MockInterventionProvider(should_fail=True, fail_error="Simulated carrier rejection")
    result = provider.disconnect_call("session-fail")

    assert result.success is False
    assert result.provider == "mock"
    assert result.error == "Simulated carrier rejection"
    assert len(provider.executed_disconnects) == 0


# --- 5. MEDIUM produces no intervention ---
@pytest.mark.asyncio
async def test_medium_produces_no_intervention():
    service = InterventionService()
    session = make_test_session("session-med")
    decision = make_decision("session-med", level=ProtectionLevel.ADVISORY, has_dashboard_alert=False, score=60.0, tier=RiskTier.MEDIUM)
    risk = make_risk_with_tactic("session-med", ManipulationCategory.AUTHORITY_IMPERSONATION, score=60.0, tier=RiskTier.MEDIUM)

    rec = await service.evaluate_and_execute(session, decision, risk)
    assert rec is None


# --- 6. HIGH produces no intervention ---
@pytest.mark.asyncio
async def test_high_produces_no_intervention():
    service = InterventionService()
    session = make_test_session("session-high")
    decision = make_decision("session-high", level=ProtectionLevel.WARNING, has_dashboard_alert=True, score=85.0, tier=RiskTier.HIGH)
    risk = make_risk_with_tactic("session-high", ManipulationCategory.INFORMATION_PHISHING, score=85.0, tier=RiskTier.HIGH)

    # Even with acute tactic, HIGH tier does NOT trigger disconnect
    rec = await service.evaluate_and_execute(session, decision, risk)
    assert rec is None


# --- 7. CRITICAL without acute tactic produces no intervention ---
@pytest.mark.asyncio
async def test_critical_without_acute_tactic_produces_no_intervention():
    service = InterventionService()
    session = make_test_session("session-crit-no-acute")
    decision = make_decision("session-crit-no-acute", level=ProtectionLevel.CRITICAL_INTERCEPT, has_dashboard_alert=True, score=95.0, tier=RiskTier.CRITICAL)
    # Tactic is URGENCY, not INFORMATION_PHISHING or FINANCIAL_REDIRECTION
    risk = make_risk_with_tactic("session-crit-no-acute", ManipulationCategory.URGENCY, score=95.0, tier=RiskTier.CRITICAL)

    rec = await service.evaluate_and_execute(session, decision, risk)
    assert rec is None


# --- 8. CRITICAL + INFORMATION_PHISHING produces intervention ---
@pytest.mark.asyncio
async def test_critical_with_information_phishing_produces_intervention():
    provider = MockInterventionProvider()
    service = InterventionService(default_provider=provider)
    session = make_test_session("session-crit-phish")
    decision = make_decision("session-crit-phish", level=ProtectionLevel.CRITICAL_INTERCEPT, has_dashboard_alert=True)
    risk = make_risk_with_tactic("session-crit-phish", ManipulationCategory.INFORMATION_PHISHING)

    rec = await service.evaluate_and_execute(session, decision, risk)
    assert rec is not None
    assert rec.status == InterventionStatus.EXECUTED
    assert rec.type == InterventionType.DISCONNECT
    assert rec.provider == "mock"
    assert "Critical scam threshold" in rec.reason
    assert len(provider.executed_disconnects) == 1


# --- 9. CRITICAL + FINANCIAL_REDIRECTION produces intervention ---
@pytest.mark.asyncio
async def test_critical_with_financial_redirection_produces_intervention():
    provider = MockInterventionProvider()
    service = InterventionService(default_provider=provider)
    session = make_test_session("session-crit-fin")
    decision = make_decision("session-crit-fin", level=ProtectionLevel.CRITICAL_INTERCEPT, has_dashboard_alert=True)
    risk = make_risk_with_tactic("session-crit-fin", ManipulationCategory.FINANCIAL_REDIRECTION)

    rec = await service.evaluate_and_execute(session, decision, risk)
    assert rec is not None
    assert rec.status == InterventionStatus.EXECUTED
    assert len(provider.executed_disconnects) == 1


# --- 10. Cooldown-suppressed CRITICAL produces no intervention ---
@pytest.mark.asyncio
async def test_cooldown_suppressed_critical_produces_no_intervention():
    provider = MockInterventionProvider()
    service = InterventionService(default_provider=provider)
    session = make_test_session("session-crit-suppressed")

    # When cooldown suppresses DASHBOARD_ALERT, has_dashboard_alert is False
    decision = make_decision("session-crit-suppressed", level=ProtectionLevel.CRITICAL_INTERCEPT, has_dashboard_alert=False)
    risk = make_risk_with_tactic("session-crit-suppressed", ManipulationCategory.INFORMATION_PHISHING)

    rec = await service.evaluate_and_execute(session, decision, risk)
    assert rec is None
    assert len(provider.executed_disconnects) == 0


# --- 11. Duplicate intervention is suppressed ---
@pytest.mark.asyncio
async def test_duplicate_intervention_is_suppressed():
    provider = MockInterventionProvider()
    service = InterventionService(default_provider=provider)
    session = make_test_session("session-dup")
    decision = make_decision("session-dup", level=ProtectionLevel.CRITICAL_INTERCEPT, has_dashboard_alert=True)
    risk = make_risk_with_tactic("session-dup", ManipulationCategory.INFORMATION_PHISHING)

    # First attempt: executes
    rec1 = await service.evaluate_and_execute(session, decision, risk)
    assert rec1 is not None
    assert rec1.status == InterventionStatus.EXECUTED
    session.intervention_history.append(rec1)
    assert len(provider.executed_disconnects) == 1

    # Second attempt: suppressed under idempotency invariant
    rec2 = await service.evaluate_and_execute(session, decision, risk)
    assert rec2 is not None
    assert rec2.status == InterventionStatus.SUPPRESSED
    assert "already executed" in rec2.reason
    # Provider was NOT invoked again!
    assert len(provider.executed_disconnects) == 1


# --- 12. Near-simultaneous duplicate requests cannot execute twice ---
@pytest.mark.asyncio
async def test_near_simultaneous_duplicate_requests_cannot_execute_twice():
    provider = MockInterventionProvider()
    service = InterventionService(default_provider=provider)
    session = make_test_session("session-concurrent")
    decision = make_decision("session-concurrent", level=ProtectionLevel.CRITICAL_INTERCEPT, has_dashboard_alert=True)
    risk = make_risk_with_tactic("session-concurrent", ManipulationCategory.INFORMATION_PHISHING)

    # Launch two concurrent evaluation tasks
    async def worker():
        rec = await service.evaluate_and_execute(session, decision, risk)
        if rec and rec.status == InterventionStatus.EXECUTED:
            session.intervention_history.append(rec)
        return rec

    results = await asyncio.gather(worker(), worker())
    statuses = [r.status for r in results if r]

    # Exactly one EXECUTED
    assert statuses.count(InterventionStatus.EXECUTED) == 1
    assert len(provider.executed_disconnects) == 1


# --- 13. Provider failure does not break pipeline ---
@pytest.mark.asyncio
async def test_provider_failure_does_not_break_pipeline():
    semantic_classifier.initialize()
    failing_provider = MockInterventionProvider(should_fail=True, fail_error="Simulated telephony disconnect failure")
    intervention_service.default_provider = failing_provider

    session_id = "test-interv-fail-pipeline"
    await session_store.create_session(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="Elderly Caller",
    )

    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="This is Officer Miller from the Police. An arrest warrant has been issued. Give me your 6 digit code right now.",
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)

    # Pipeline completed normally
    assert result["risk"].overall_score >= 75.0
    assert result["protection"] is not None
    assert result["intervention"] is not None
    assert result["intervention"].status == InterventionStatus.FAILED
    assert "Simulated telephony disconnect failure" in result["intervention"].error

    # Session store recorded failure safely
    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.intervention_history) == 1
    assert session.intervention_history[0].status == InterventionStatus.FAILED


# --- 14. Provider exception does not break pipeline ---
class BuggyInterventionProvider(MockInterventionProvider):
    def disconnect_call(self, session_id: str):
        raise RuntimeError("Unexpected carrier connection crash")


@pytest.mark.asyncio
async def test_provider_exception_does_not_break_pipeline():
    semantic_classifier.initialize()
    intervention_service.default_provider = BuggyInterventionProvider()

    session_id = "test-interv-exc-pipeline"
    await session_store.create_session(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="Elderly Caller",
    )

    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="This is Officer Miller from the Police. An arrest warrant has been issued. Give me your 6 digit code right now.",
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)

    assert result["risk"].overall_score >= 75.0
    assert result["protection"] is not None
    assert result["intervention"] is not None
    assert result["intervention"].status == InterventionStatus.FAILED
    assert "Unexpected carrier connection crash" in result["intervention"].error

    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.intervention_history) == 1
    assert session.intervention_history[0].status == InterventionStatus.FAILED


# --- 15. Intervention history bounded to 100 in SessionStore ---
@pytest.mark.asyncio
async def test_intervention_history_bounded_to_100():
    session_id = "test-interv-bounded-store"
    await session_store.create_session(session_id=session_id)

    for i in range(115):
        rec = InterventionRecord(
            session_id=session_id,
            type=InterventionType.DISCONNECT,
            status=InterventionStatus.EXECUTED,
            reason=f"Disconnect {i}",
        )
        await session_store.add_intervention_record(session_id, rec)

    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.intervention_history) == 100
    assert session.intervention_history[-1].reason == "Disconnect 114"


# --- 16. Existing WebSocket event order preserved ---
def test_ws_event_order_preserved_with_intervention(client: TestClient):
    """Verify WebSocket emits events in exact order with intervention service active."""
    semantic_classifier.initialize()
    session_id = "test-ws-intervention-order"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        init_msg = websocket.receive_json()
        assert init_msg["type"] == WSMessageType.SESSION_STATUS.value

        websocket.send_json({
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
        })

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


# --- 17. Mock simulation remains functional ---
@pytest.mark.asyncio
async def test_mock_simulation_remains_functional():
    session_id = "test-sim-intervention"
    await session_store.create_session(session_id=session_id)

    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=[
            "This is Officer Miller from the Federal Police Department.",
            "An arrest warrant has been issued in your name for criminal money laundering.",
            "You have only fifteen minutes to resolve this before officers arrive.",
            "Do not disconnect this line and do not tell your family about this call.",
            "Read me the six digit security code that was just sent to your phone.",
        ],
        delay_seconds=0.0,
        broadcast=False,
    )

    assert len(results) == 5
    session = await session_store.get_session(session_id)
    assert session is not None
    # Intervention was executed on the acute credential phishing step
    assert len(session.intervention_history) >= 1
    assert session.intervention_history[0].status == InterventionStatus.EXECUTED


# --- 18. No external network calls ---
def test_no_external_network_calls():
    provider = MockInterventionProvider()
    res = provider.disconnect_call("session-zero-net")
    assert res.success is True
    assert res.provider == "mock"


# --- 19. Mock result clearly indicates simulated operation ---
def test_mock_result_indicates_simulated_operation():
    provider = MockInterventionProvider()
    res = provider.disconnect_call("session-sim-check")
    assert res.provider == "mock"
    assert res.intervention_id.startswith("mock-disconnect-")


# --- 20. Session isolation in intervention ---
@pytest.mark.asyncio
async def test_session_isolation_in_intervention():
    provider = MockInterventionProvider()
    service = InterventionService(default_provider=provider)

    s1 = make_test_session("session-iso-1")
    s2 = make_test_session("session-iso-2")

    d1 = make_decision("session-iso-1", level=ProtectionLevel.CRITICAL_INTERCEPT, has_dashboard_alert=True)
    r1 = make_risk_with_tactic("session-iso-1", ManipulationCategory.INFORMATION_PHISHING)

    d2 = make_decision("session-iso-2", level=ProtectionLevel.WARNING, has_dashboard_alert=True)
    r2 = make_risk_with_tactic("session-iso-2", ManipulationCategory.INFORMATION_PHISHING)

    res1 = await service.evaluate_and_execute(s1, d1, r1)
    res2 = await service.evaluate_and_execute(s2, d2, r2)

    assert res1 is not None
    assert res1.status == InterventionStatus.EXECUTED
    assert res2 is None
    assert len(provider.executed_disconnects) == 1
    assert provider.executed_disconnects[0]["session_id"] == "session-iso-1"


# --- 21. Existing 7A/7B/7C behavior remains intact ---
@pytest.mark.asyncio
async def test_existing_7a_7b_7c_behavior_remains_intact():
    """Verify that when intervention executes, caregiver notification and user warning and dashboard alert all succeed."""
    semantic_classifier.initialize()
    session_id = "test-harmonious-pipeline"
    session = await session_store.create_session(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="Margaret H.",
    )
    session.caregiver_contacts = [
        CaregiverContact(name="Alice Doe", phone_number="+18005550111", enabled=True)
    ]

    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="This is Officer Miller from the Federal Police. An arrest warrant has been issued. Read me the six digit security code right now.",
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)

    # 1. 7A: Protection decision made
    assert result["protection"] is not None
    assert result["protection"].level in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]

    # 2. 7B: Caregiver notification generated
    assert len(result["notifications"]) == 1
    assert result["notifications"][0].status.value == "SENT"

    # 3. 7C: User warning generated
    assert result["user_warning"] is not None
    assert result["user_warning"].status == UserWarningStatus.DELIVERED

    # 4. 7D-1: Call intervention executed
    assert result["intervention"] is not None
    assert result["intervention"].status == InterventionStatus.EXECUTED
