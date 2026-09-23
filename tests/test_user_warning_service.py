import time
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models import (
    CallSession,
    ProtectionAction,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    ProtectionLevel,
    RiskTier,
    SpeakerType,
    TranscriptSegment,
    UserWarningChannel,
    UserWarningRecord,
    UserWarningStatus,
    WSMessageType,
)
from backend.app.services.user_warning_service import (
    MockUserWarningProvider,
    ProtectedUserWarningService,
    protected_user_warning_service,
)
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.protection_engine import protection_engine
from backend.app.services.session_store import session_store
from ai.classifier import semantic_classifier


@pytest.fixture(autouse=True)
def cleanup_state():
    """Reset protection engine and user warning provider before and after each test."""
    protection_engine.clear()
    protected_user_warning_service.default_provider = MockUserWarningProvider()
    yield
    protection_engine.clear()
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
    score: float = 80.0,
    tier: RiskTier = RiskTier.HIGH,
    is_escalation: bool = False,
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
        is_escalation=is_escalation,
        explanation="Test explanation",
    )


# --- 1. User warning model defaults ---
def test_user_warning_model_defaults():
    rec = UserWarningRecord(
        session_id="test-session-defaults",
        message="Test alert message",
        status=UserWarningStatus.DELIVERED,
    )
    assert rec.session_id == "test-session-defaults"
    assert rec.channel == UserWarningChannel.VOICE
    assert rec.status == UserWarningStatus.DELIVERED
    assert rec.provider == "mock"
    assert rec.warning_id is not None
    assert rec.error is None

    session = CallSession()
    assert isinstance(session.user_warning_history, list)
    assert len(session.user_warning_history) == 0


# --- 2. Session warning-history isolation ---
def test_session_warning_history_isolation():
    session_a = CallSession(session_id="session-warn-a")
    session_b = CallSession(session_id="session-warn-b")

    rec_a = UserWarningRecord(
        session_id="session-warn-a",
        message="Warning A",
        status=UserWarningStatus.DELIVERED,
    )
    session_a.user_warning_history.append(rec_a)

    assert len(session_a.user_warning_history) == 1
    assert len(session_b.user_warning_history) == 0
    assert session_a.user_warning_history[0].message == "Warning A"


# --- 3. Mock warning success ---
def test_mock_warning_success():
    provider = MockUserWarningProvider()
    result = provider.warn_user("session-success", "Calm warning message")

    assert result.success is True
    assert result.provider == "mock"
    assert result.warning_id is not None
    assert result.warning_id.startswith("mock-warning-")
    assert result.error is None
    assert len(provider.delivered_warnings) == 1
    assert provider.delivered_warnings[0]["session_id"] == "session-success"


# --- 4. Mock warning failure ---
def test_mock_warning_failure():
    provider = MockUserWarningProvider(should_fail=True, fail_error="Audio channel busy")
    result = provider.warn_user("session-fail", "Warning message")

    assert result.success is False
    assert result.provider == "mock"
    assert result.error == "Audio channel busy"
    assert len(provider.delivered_warnings) == 0


# --- 5. MEDIUM produces no user warning ---
def test_medium_produces_no_user_warning():
    service = ProtectedUserWarningService()
    session = make_test_session("session-med")
    decision = make_decision(
        "session-med",
        level=ProtectionLevel.ADVISORY,
        has_dashboard_alert=False,
        score=60.0,
        tier=RiskTier.MEDIUM,
    )

    rec = service.warn_user(session, decision)
    assert rec is None


# --- 6. First HIGH produces user warning ---
def test_first_high_produces_user_warning():
    provider = MockUserWarningProvider()
    service = ProtectedUserWarningService(default_provider=provider)
    session = make_test_session("session-high")
    decision = make_decision(
        "session-high",
        level=ProtectionLevel.WARNING,
        has_dashboard_alert=True,
        score=78.0,
        tier=RiskTier.HIGH,
    )

    rec = service.warn_user(session, decision)
    assert rec is not None
    assert rec.status == UserWarningStatus.DELIVERED
    assert rec.channel == UserWarningChannel.VOICE
    assert "Please be careful. This call may be suspicious." in rec.message
    assert "Do not share OTPs, passwords, or banking details." in rec.message
    assert len(provider.delivered_warnings) == 1


# --- 7. CRITICAL produces user warning ---
def test_critical_produces_user_warning():
    provider = MockUserWarningProvider()
    service = ProtectedUserWarningService(default_provider=provider)
    session = make_test_session("session-crit")
    decision = make_decision(
        "session-crit",
        level=ProtectionLevel.CRITICAL_INTERCEPT,
        has_dashboard_alert=True,
        score=95.0,
        tier=RiskTier.CRITICAL,
    )

    rec = service.warn_user(session, decision)
    assert rec is not None
    assert rec.status == UserWarningStatus.DELIVERED
    assert "Warning. This call appears highly suspicious." in rec.message
    assert "Consider ending the call." in rec.message
    assert len(provider.delivered_warnings) == 1


# --- 8. Cooldown-suppressed HIGH produces no warning ---
def test_cooldown_suppressed_high_produces_no_warning():
    provider = MockUserWarningProvider()
    service = ProtectedUserWarningService(default_provider=provider)
    session = make_test_session("session-cooldown")

    # In cooldown, has_dashboard_alert is False because DASHBOARD_ALERT wasn't EXECUTED
    decision = make_decision(
        "session-cooldown",
        level=ProtectionLevel.WARNING,
        has_dashboard_alert=False,
        score=82.0,
        tier=RiskTier.HIGH,
    )

    rec = service.warn_user(session, decision)
    assert rec is None
    assert len(provider.delivered_warnings) == 0


# --- 9. HIGH -> CRITICAL escalation produces warning ---
def test_high_to_critical_escalation_produces_warning():
    provider = MockUserWarningProvider()
    service = ProtectedUserWarningService(default_provider=provider)
    session = make_test_session("session-escalate")

    decision = make_decision(
        "session-escalate",
        level=ProtectionLevel.CRITICAL_INTERCEPT,
        has_dashboard_alert=True,
        score=95.0,
        tier=RiskTier.CRITICAL,
        is_escalation=True,
    )

    rec = service.warn_user(session, decision)
    assert rec is not None
    assert rec.status == UserWarningStatus.DELIVERED
    assert "Consider ending the call." in rec.message
    assert len(provider.delivered_warnings) == 1


# --- 10. Provider failure does not break pipeline ---
@pytest.mark.asyncio
async def test_provider_failure_does_not_break_pipeline():
    semantic_classifier.initialize()
    failing_provider = MockUserWarningProvider(should_fail=True, fail_error="Voice synthesis offline")
    protected_user_warning_service.default_provider = failing_provider

    session_id = "test-warn-fail-pipeline"
    await session_store.create_session(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="Elderly Caller",
    )

    # Critical scam segment
    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="This is Officer Miller from the Police. An arrest warrant has been issued. Give me your 6 digit code right now.",
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)

    # Pipeline completed normally
    assert result["risk"].overall_score >= 75.0
    assert result["protection"] is not None
    assert result["user_warning"] is not None
    assert result["user_warning"].status == UserWarningStatus.FAILED
    assert "Voice synthesis offline" in result["user_warning"].error

    # Session store recorded failure safely
    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.user_warning_history) == 1
    assert session.user_warning_history[0].status == UserWarningStatus.FAILED


# --- 11. Provider exception does not break pipeline ---
class BuggyUserWarningProvider(MockUserWarningProvider):
    def warn_user(self, session_id: str, message: str):
        raise RuntimeError("Unexpected audio hardware fault")


@pytest.mark.asyncio
async def test_provider_exception_does_not_break_pipeline():
    semantic_classifier.initialize()
    protected_user_warning_service.default_provider = BuggyUserWarningProvider()

    session_id = "test-warn-exc-pipeline"
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
    assert result["user_warning"] is not None
    assert result["user_warning"].status == UserWarningStatus.FAILED
    assert "Unexpected audio hardware fault" in result["user_warning"].error

    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.user_warning_history) == 1
    assert session.user_warning_history[0].status == UserWarningStatus.FAILED


# --- 12. Warning history bounded to 100 in SessionStore ---
@pytest.mark.asyncio
async def test_warning_history_bounded_to_100():
    session_id = "test-warn-bounded-store"
    await session_store.create_session(session_id=session_id)

    for i in range(115):
        rec = UserWarningRecord(
            session_id=session_id,
            channel=UserWarningChannel.VOICE,
            message=f"Warning message {i}",
            status=UserWarningStatus.DELIVERED,
        )
        await session_store.add_user_warning_record(session_id, rec)

    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.user_warning_history) == 100
    # Last record should be message 114
    assert session.user_warning_history[-1].message == "Warning message 114"


# --- 13. Existing WebSocket event order preserved ---
def test_ws_event_order_preserved_with_user_warnings(client: TestClient):
    """Verify WebSocket emits events in exact order with protected user warning active."""
    semantic_classifier.initialize()
    session_id = "test-ws-user-warning-order"

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


# --- 14. No external network calls (Mock provider verification) ---
def test_no_external_network_calls():
    provider = MockUserWarningProvider()
    res = provider.warn_user("session-zero-net", "Zero network call test")
    assert res.success is True
    assert res.provider == "mock"


# --- 15. Mock simulation still works ---
@pytest.mark.asyncio
async def test_mock_simulation_with_user_warning_service():
    session_id = "test-sim-user-warning"
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
    assert len(session.user_warning_history) >= 1
    assert session.user_warning_history[0].status == UserWarningStatus.DELIVERED


# --- 16. Warning message is privacy-safe ---
def test_warning_message_privacy_safe():
    service = ProtectedUserWarningService()
    decision = make_decision("test-session", level=ProtectionLevel.WARNING, score=85.0)
    msg = service.build_warning_message(decision)

    # Must NOT contain technical or internal scoring details
    assert "AI detected" not in msg
    assert "85" not in msg
    assert "score" not in msg.lower()
    assert "tactic" not in msg.lower()
    assert "transcript" not in msg.lower()
    assert "model" not in msg.lower()


# --- 17. Warning message differs appropriately between HIGH and CRITICAL ---
def test_warning_message_differs_high_vs_critical():
    service = ProtectedUserWarningService()
    high_decision = make_decision("session-h", level=ProtectionLevel.WARNING)
    crit_decision = make_decision("session-c", level=ProtectionLevel.CRITICAL_INTERCEPT)

    high_msg = service.build_warning_message(high_decision)
    crit_msg = service.build_warning_message(crit_decision)

    assert high_msg != crit_msg
    assert "Please be careful" in high_msg
    assert "Consider ending the call" in crit_msg
