import time
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models import (
    CallSession,
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
    WSMessageType,
)
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.protection_engine import (
    ALERT_COOLDOWN_SECONDS,
    ProtectionEngine,
    protection_engine,
)
from backend.app.services.session_store import session_store
from ai.classifier import semantic_classifier


@pytest.fixture(autouse=True)
def reset_protection_state():
    """Ensure clean in-memory protection state for every test."""
    protection_engine.clear()
    yield
    protection_engine.clear()


# Helper to construct RiskAssessment for unit testing
def make_risk_assessment(
    score: float,
    tier: RiskTier,
    triggered_tactics=None,
    accumulated_tactics=None,
    explanation="Test risk assessment",
    timestamp=None,
) -> RiskAssessment:
    return RiskAssessment(
        session_id="test-session",
        overall_score=score,
        risk_tier=tier,
        triggered_tactics=triggered_tactics or [],
        accumulated_tactics=accumulated_tactics or [],
        evidence_segments=[],
        tactic_evidence={},
        score_delta=0.0,
        explanation=explanation,
        timestamp=timestamp or time.time(),
    )


# --- 1. SAFE produces MONITORING ---
def test_safe_tier_produces_monitoring():
    engine = ProtectionEngine()
    risk = make_risk_assessment(score=10.0, tier=RiskTier.SAFE)
    decision = engine.evaluate("session-safe", risk, current_time=100.0)

    assert decision.level == ProtectionLevel.MONITORING
    assert decision.trigger_score == 10.0
    assert decision.trigger_tier == RiskTier.SAFE
    assert len(decision.triggered_actions) == 0
    assert decision.cooldown_applied is False
    assert decision.is_escalation is False


# --- 2. LOW produces MONITORING ---
def test_low_tier_produces_monitoring():
    engine = ProtectionEngine()
    risk = make_risk_assessment(score=35.0, tier=RiskTier.LOW)
    decision = engine.evaluate("session-low", risk, current_time=100.0)

    assert decision.level == ProtectionLevel.MONITORING
    assert len(decision.triggered_actions) == 0
    assert decision.cooldown_applied is False
    assert decision.is_escalation is False


# --- 3. MEDIUM produces ADVISORY without dashboard alert ---
def test_medium_tier_produces_advisory_without_alert():
    engine = ProtectionEngine()
    risk = make_risk_assessment(score=65.0, tier=RiskTier.MEDIUM)
    decision = engine.evaluate("session-med", risk, current_time=100.0)

    assert decision.level == ProtectionLevel.ADVISORY
    assert len(decision.triggered_actions) == 0
    assert decision.cooldown_applied is False
    assert decision.is_escalation is False
    assert "advisory monitoring active" in decision.explanation


# --- 4. First HIGH produces WARNING + DASHBOARD_ALERT ---
def test_first_high_tier_produces_warning_and_dashboard_alert():
    engine = ProtectionEngine()
    risk = make_risk_assessment(score=78.0, tier=RiskTier.HIGH)
    decision = engine.evaluate("session-high", risk, current_time=100.0)

    assert decision.level == ProtectionLevel.WARNING
    assert len(decision.triggered_actions) == 1
    action = decision.triggered_actions[0]
    assert action.action_type == ProtectionActionType.DASHBOARD_ALERT
    assert action.level == ProtectionLevel.WARNING
    assert action.status == ProtectionActionStatus.EXECUTED
    assert action.recipient == "dashboard"
    assert decision.cooldown_applied is False


# --- 5. Repeated HIGH inside cooldown is suppressed ---
def test_repeated_high_inside_cooldown_is_suppressed():
    engine = ProtectionEngine(cooldown_seconds=20.0)
    risk1 = make_risk_assessment(score=78.0, tier=RiskTier.HIGH)
    d1 = engine.evaluate("session-repeat", risk1, current_time=100.0)
    assert len(d1.triggered_actions) == 1
    assert d1.cooldown_applied is False

    # Repeated HIGH 5 seconds later (within 20s window)
    risk2 = make_risk_assessment(score=82.0, tier=RiskTier.HIGH)
    d2 = engine.evaluate("session-repeat", risk2, current_time=105.0)
    assert d2.level == ProtectionLevel.WARNING
    assert len(d2.triggered_actions) == 0
    assert d2.cooldown_applied is True
    assert "suppressed under 20s cooldown" in d2.explanation


# --- 6. HIGH after cooldown can alert again ---
def test_high_after_cooldown_can_alert_again():
    engine = ProtectionEngine(cooldown_seconds=20.0)
    risk1 = make_risk_assessment(score=78.0, tier=RiskTier.HIGH)
    d1 = engine.evaluate("session-cooldown-expire", risk1, current_time=100.0)
    assert len(d1.triggered_actions) == 1

    # Same tier after 21 seconds (outside 20s window)
    risk2 = make_risk_assessment(score=80.0, tier=RiskTier.HIGH)
    d2 = engine.evaluate("session-cooldown-expire", risk2, current_time=121.0)
    assert d2.level == ProtectionLevel.WARNING
    assert len(d2.triggered_actions) == 1
    assert d2.triggered_actions[0].action_type == ProtectionActionType.DASHBOARD_ALERT
    assert d2.cooldown_applied is False


# --- 7. HIGH -> CRITICAL bypasses cooldown ---
def test_high_to_critical_escalation_bypasses_cooldown():
    engine = ProtectionEngine(cooldown_seconds=20.0)
    risk_high = make_risk_assessment(score=78.0, tier=RiskTier.HIGH)
    d1 = engine.evaluate("session-escalate", risk_high, current_time=100.0)
    assert d1.level == ProtectionLevel.WARNING
    assert len(d1.triggered_actions) == 1

    # Escalation to CRITICAL only 5s later (inside 20s cooldown)
    risk_crit = make_risk_assessment(score=94.0, tier=RiskTier.CRITICAL)
    d2 = engine.evaluate("session-escalate", risk_crit, current_time=105.0)

    assert d2.level == ProtectionLevel.CRITICAL_INTERCEPT
    assert d2.is_escalation is True
    assert d2.cooldown_applied is False
    assert len(d2.triggered_actions) == 1
    assert d2.triggered_actions[0].action_type == ProtectionActionType.DASHBOARD_ALERT
    assert d2.triggered_actions[0].level == ProtectionLevel.CRITICAL_INTERCEPT
    assert "bypassed cooldown" in d2.explanation


# --- 8. Repeated CRITICAL inside cooldown is suppressed unless acute escalation rule applies ---
def test_repeated_critical_cooldown_and_acute_tactic_bypass():
    engine = ProtectionEngine(cooldown_seconds=20.0)
    risk_crit1 = make_risk_assessment(score=92.0, tier=RiskTier.CRITICAL)
    d1 = engine.evaluate("session-crit-cooldown", risk_crit1, current_time=100.0)
    assert len(d1.triggered_actions) == 1

    # Repeated CRITICAL 5 seconds later with ordinary tactics -> suppressed
    risk_crit2 = make_risk_assessment(score=93.0, tier=RiskTier.CRITICAL)
    d2 = engine.evaluate("session-crit-cooldown", risk_crit2, current_time=105.0)
    assert d2.cooldown_applied is True
    assert len(d2.triggered_actions) == 0

    # Acute extraction tactic arrives (e.g. OTP harvesting / INFORMATION_PHISHING) -> bypasses cooldown!
    otp_match = TacticMatch(
        tactic=ManipulationCategory.INFORMATION_PHISHING,
        confidence=0.95,
        evidence_text="Give me your 6-digit verification code",
    )
    risk_crit3 = make_risk_assessment(
        score=96.0,
        tier=RiskTier.CRITICAL,
        triggered_tactics=[otp_match],
    )
    d3 = engine.evaluate("session-crit-cooldown", risk_crit3, current_time=108.0)
    assert d3.is_escalation is True
    assert d3.cooldown_applied is False
    assert len(d3.triggered_actions) == 1
    assert "Acute extraction tactic" in d3.explanation


# --- 9. Session A cooldown does not affect Session B ---
def test_session_isolation_cooldown():
    engine = ProtectionEngine(cooldown_seconds=20.0)
    risk = make_risk_assessment(score=80.0, tier=RiskTier.HIGH)

    # Session A triggers alert at t=100
    da1 = engine.evaluate("session-A", risk, current_time=100.0)
    assert len(da1.triggered_actions) == 1

    # Session A repeated at t=102 -> suppressed
    da2 = engine.evaluate("session-A", risk, current_time=102.0)
    assert len(da2.triggered_actions) == 0
    assert da2.cooldown_applied is True

    # Session B triggers at t=103 -> MUST NOT be suppressed by Session A!
    db1 = engine.evaluate("session-B", risk, current_time=103.0)
    assert len(db1.triggered_actions) == 1
    assert db1.cooldown_applied is False


# --- 10. Protection history is recorded correctly in SessionStore ---
@pytest.mark.asyncio
async def test_protection_history_recorded_in_session_store():
    session = await session_store.create_session(session_id="test-store-history-01")
    assert len(session.protection_history) == 0

    decision = ProtectionDecision(
        session_id="test-store-history-01",
        level=ProtectionLevel.WARNING,
        triggered_actions=[
            ProtectionAction(
                action_type=ProtectionActionType.DASHBOARD_ALERT,
                level=ProtectionLevel.WARNING,
                message="Test warning",
            )
        ],
        trigger_score=80.0,
        trigger_tier=RiskTier.HIGH,
        explanation="Test explanation",
    )

    await session_store.add_protection_decision("test-store-history-01", decision)
    retrieved = await session_store.get_session("test-store-history-01")
    assert retrieved is not None
    assert len(retrieved.protection_history) == 1
    assert retrieved.protection_history[0].level == ProtectionLevel.WARNING
    assert retrieved.protection_history[0].trigger_score == 80.0


# --- 11. Existing ALERT_TRIGGERED payload remains backward compatible ---
# --- 12. Existing WebSocket event ordering remains unchanged ---
def test_ws_event_sequence_and_backward_compatibility(client: TestClient):
    """Verify WebSocket emits events in exact sequence with backward-compatible ALERT_TRIGGERED data."""
    semantic_classifier.initialize()
    session_id = "test-ws-protection-compat"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        # Drain initial SESSION_STATUS
        init_msg = websocket.receive_json()
        assert init_msg["type"] == WSMessageType.SESSION_STATUS.value

        # Send multi-tactic critical scam phrase
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

        # Event 4: ALERT_TRIGGERED (governed by ProtectionEngine)
        e4 = websocket.receive_json()
        assert e4["type"] == WSMessageType.ALERT_TRIGGERED.value
        data = e4["data"]

        # Verify all existing required backward-compatible fields
        assert data["session_id"] == session_id
        assert "overall_score" in data
        assert "risk_tier" in data
        assert data["risk_tier"] in ["HIGH", "CRITICAL"]
        assert "accumulated_tactics" in data
        assert "explanation" in data
        assert "latest_evidence" in data

        # Verify new Phase 7A protection metadata
        assert "protection_level" in data
        assert data["protection_level"] in [ProtectionLevel.WARNING.value, ProtectionLevel.CRITICAL_INTERCEPT.value]
        assert "is_escalation" in data
        assert "cooldown_applied" in data


# --- 14. Mock simulation still produces expected dashboard behavior ---
@pytest.mark.asyncio
async def test_mock_simulation_drives_protection_engine():
    """Verify mock STT simulation produces protection decisions through the pipeline."""
    session_id = "test-sim-protection-engine"
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
    # Step 1 should have lower risk, step 5 should be high/critical
    last_step = results[-1]
    assert "protection" in last_step
    last_decision: ProtectionDecision = last_step["protection"]
    assert last_decision is not None
    assert last_decision.level in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]

    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.protection_history) == 5
