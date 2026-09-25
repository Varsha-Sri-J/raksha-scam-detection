"""End-to-End QA Integration Scenarios for RAKSHA Pipeline.

Exercises the complete RAKSHA pipeline end-to-end:
  TranscriptSegment (Input)
         ↓
  SemanticClassifier (Scam Classification & Tactic Detection)
         ↓
  RiskEngine (Dynamic Risk Calculation)
         ↓
  ProtectionEngine (Policy Evaluation & Cooldown Governance)
         ↓
  Downstream Services (Caregiver SMS, User Voice Warning, Call Intervention)

Test Scenarios:
1. Clearly benign conversation
2. Clearly malicious/scam conversation
3. Multi-tactic scam conversation
4. Legitimate urgent conversation
5. Scam risk increasing across multiple turns
6. Duplicate critical events / cooldown behavior
7. Downstream notification/protection failure
8. Recovery after a failure
"""

import asyncio
import pytest
from typing import List

from backend.app.models import (
    CallSession,
    CaregiverContact,
    InterventionStatus,
    ManipulationCategory,
    NotificationStatus,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionLevel,
    RiskTier,
    SpeakerType,
    TranscriptSegment,
    UserWarningStatus,
    WSMessageType,
)
from backend.app.services.pipeline import StreamingPipeline
from backend.app.services.session_store import session_store
from backend.app.services.protection_engine import protection_engine
from backend.app.services.notification_service import (
    caregiver_notification_service,
    MockSMSProvider,
)
from backend.app.services.user_warning_service import (
    protected_user_warning_service,
    MockUserWarningProvider,
)
from backend.app.services.intervention_service import (
    intervention_service,
    MockInterventionProvider,
)
from ai.classifier import semantic_classifier


@pytest.fixture(scope="module", autouse=True)
def init_classifier():
    """Ensure semantic classifier is initialized for E2E tests."""
    semantic_classifier.initialize()


@pytest.fixture(autouse=True)
def reset_pipeline_services():
    """Reset protection engine states and re-assign default mock providers before each test."""
    protection_engine.clear()
    caregiver_notification_service.default_provider = MockSMSProvider()
    protected_user_warning_service.default_provider = MockUserWarningProvider()
    intervention_service.default_provider = MockInterventionProvider()
    yield
    protection_engine.clear()
    caregiver_notification_service.default_provider = MockSMSProvider()
    protected_user_warning_service.default_provider = MockUserWarningProvider()
    intervention_service.default_provider = MockInterventionProvider()


async def create_test_session(session_id: str) -> CallSession:
    """Helper to initialize a test CallSession with caregiver contact configured."""
    session = await session_store.create_session(session_id=session_id)
    session.callee_id = "Protected User (Margaret)"
    session.caregiver_contacts = [
        CaregiverContact(name="Primary Caregiver", phone_number="+15551234567", enabled=True)
    ]
    session.protected_user_connected = True
    return session


# ==============================================================================
# Scenario 1: Clearly Benign Conversation
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_clearly_benign_conversation():
    """Verify that a benign everyday conversation produces zero scam alerts or downstream interventions."""
    session_id = "e2e-benign-001"
    await create_test_session(session_id)
    pipeline = StreamingPipeline()

    utterances = [
        "Hi Grandma, just calling to see how you are doing this afternoon.",
        "I was wondering if you wanted to go get lunch together tomorrow at the diner.",
        "That sounds wonderful! I will pick you up around noon. Have a great day!",
    ]

    for idx, text in enumerate(utterances):
        segment = TranscriptSegment(
            session_id=session_id,
            speaker=SpeakerType.CALLER if idx % 2 == 0 else SpeakerType.CALLEE,
            text=text,
            is_final=True,
            sequence_number=idx + 1,
        )
        result = await pipeline.process_segment(segment)

        # 1. Classification & Tactics
        assert result["matches"] == [], f"Expected no tactics matched for benign phrase: '{text}'"

        # 2. Risk Calculation
        risk = result["risk"]
        assert risk is not None
        assert risk.overall_score == 0.0 or risk.risk_tier == RiskTier.SAFE
        assert risk.accumulated_tactics == []

        # 3. Protection Engine
        protection = result["protection"]
        assert protection is not None
        assert protection.level == ProtectionLevel.MONITORING
        assert not any(
            action.action_type == ProtectionActionType.DASHBOARD_ALERT
            and action.status == ProtectionActionStatus.EXECUTED
            for action in protection.triggered_actions
        )

        # 4. Downstream Interventions & Notifications
        assert result["notifications"] == []
        assert result["user_warning"] is None
        assert result["intervention"] is None

    # Verify session store state
    saved_session = await session_store.get_session(session_id)
    assert saved_session is not None
    assert len(saved_session.transcript_history) == 3
    assert saved_session.latest_risk.risk_tier == RiskTier.SAFE


# ==============================================================================
# Scenario 2: Clearly Malicious / Scam Conversation
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_clearly_malicious_scam_conversation():
    """Verify that an overt scam call triggers tactic detection, high risk, dashboard alert, SMS, warning & intervention."""
    session_id = "e2e-scam-002"
    await create_test_session(session_id)
    pipeline = StreamingPipeline()

    scam_text = (
        "This is Officer Miller from the Federal Tax Police. Your bank account is compromised. "
        "You must wire $5,000 to our safe holding account immediately or face instant arrest."
    )
    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text=scam_text,
        is_final=True,
        sequence_number=1,
    )

    result = await pipeline.process_segment(segment)

    # 1. Scam Classification & Tactic Detection
    matches = result["matches"]
    matched_categories = {m.tactic for m in matches}
    assert (
        ManipulationCategory.AUTHORITY_IMPERSONATION in matched_categories
        or ManipulationCategory.FINANCIAL_REDIRECTION in matched_categories
        or ManipulationCategory.COERCIVE_URGENCY in matched_categories
    ), f"Expected scam tactics in matches, got: {matched_categories}"

    # 2. Risk Calculation
    risk = result["risk"]
    assert risk is not None
    assert risk.overall_score >= 50.0
    assert risk.risk_tier in [RiskTier.MEDIUM, RiskTier.HIGH, RiskTier.CRITICAL]

    # 3. Protection Engine
    protection = result["protection"]
    assert protection is not None
    assert protection.level in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]
    has_executed_alert = any(
        a.action_type == ProtectionActionType.DASHBOARD_ALERT
        and a.status == ProtectionActionStatus.EXECUTED
        for a in protection.triggered_actions
    )
    assert has_executed_alert, "Expected EXECUTED DASHBOARD_ALERT in protection decision"

    # 4. Downstream Interventions & Notifications
    notifications = result["notifications"]
    assert len(notifications) == 1
    assert notifications[0].status == NotificationStatus.SENT

    user_warning = result["user_warning"]
    assert user_warning is not None
    assert user_warning.status == UserWarningStatus.DELIVERED

    # Acute financial redirection tactic warrants call disconnect
    intervention = result["intervention"]
    assert intervention is not None
    assert intervention.status == InterventionStatus.EXECUTED

    # 5. Events constructed for WebSocket broadcast
    events = result["events"]
    event_types = [e.type for e in events]
    assert WSMessageType.TRANSCRIPT_UPDATE in event_types
    assert WSMessageType.TACTIC_DETECTED in event_types
    assert WSMessageType.RISK_UPDATE in event_types
    assert WSMessageType.ALERT_TRIGGERED in event_types


# ==============================================================================
# Scenario 3: Multi-Tactic Scam Conversation
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_multi_tactic_scam_conversation():
    """Verify multi-turn scam where distinct tactics accumulate and escalate risk score."""
    session_id = "e2e-multi-tactic-003"
    await create_test_session(session_id)
    pipeline = StreamingPipeline()

    turns = [
        "This is Special Agent Officer Davis calling from the Federal Bureau of Investigation Fraud Department.",
        "An unauthorized $10,000 money transfer is occurring right now! You must act within 2 minutes or your accounts will be seized!",
        "Give me your 6-digit verification OTP passcode sent to your cell phone immediately or you will be arrested!",
    ]

    previous_score = -1.0
    for idx, text in enumerate(turns):
        segment = TranscriptSegment(
            session_id=session_id,
            speaker=SpeakerType.CALLER,
            text=text,
            is_final=True,
            sequence_number=idx + 1,
        )
        res = await pipeline.process_segment(segment)
        risk = res["risk"]

        # Risk score should strictly escalate as tactics accumulate across turns
        assert risk.overall_score >= previous_score
        previous_score = risk.overall_score

    # Check final multi-tactic accumulation state
    saved_session = await session_store.get_session(session_id)
    assert saved_session is not None
    final_risk = saved_session.latest_risk
    assert final_risk is not None
    assert final_risk.risk_tier in [RiskTier.HIGH, RiskTier.CRITICAL]
    assert len(final_risk.accumulated_tactics) >= 2


# ==============================================================================
# Scenario 4: Legitimate Urgent Conversation
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_legitimate_urgent_conversation():
    """Verify that legitimate emergency calls (e.g. car breakdown) do not trigger scam interventions."""
    session_id = "e2e-urgent-004"
    await create_test_session(session_id)
    pipeline = StreamingPipeline()

    turns = [
        "Mom, my car broke down on Interstate 95 and I really need your help!",
        "Can you please call a tow truck for me right away? The tire blew out.",
        "I am sitting safely inside the vehicle on the shoulder, don't worry.",
    ]

    for idx, text in enumerate(turns):
        segment = TranscriptSegment(
            session_id=session_id,
            speaker=SpeakerType.CALLER,
            text=text,
            is_final=True,
            sequence_number=idx + 1,
        )
        res = await pipeline.process_segment(segment)
        risk = res["risk"]
        protection = res["protection"]

        # Legitimate urgency without scam tactics must stay below scam alert threshold
        assert risk.risk_tier in [RiskTier.SAFE, RiskTier.LOW]
        assert protection.level == ProtectionLevel.MONITORING
        assert res["notifications"] == []
        assert res["user_warning"] is None
        assert res["intervention"] is None


# ==============================================================================
# Scenario 5: Scam Risk Increasing Across Multiple Turns
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_scam_risk_increasing_across_turns():
    """Verify progressive risk and protection level escalation over multi-turn conversation."""
    session_id = "e2e-progression-005"
    await create_test_session(session_id)
    pipeline = StreamingPipeline()

    turns = [
        "Hello, I am calling from global tech support regarding your home internet connection.",
        "We detected a severe security breach on your computer right now.",
        "This is Officer Miller from the Federal Tax Police. You must wire $5,000 to our safe holding account immediately or face instant arrest.",
    ]

    scores = []
    levels = []

    for idx, text in enumerate(turns):
        segment = TranscriptSegment(
            session_id=session_id,
            speaker=SpeakerType.CALLER,
            text=text,
            is_final=True,
            sequence_number=idx + 1,
        )
        res = await pipeline.process_segment(segment)
        scores.append(res["risk"].overall_score)
        levels.append(res["protection"].level)

    # Verify score strictly increases across turns
    assert scores[0] <= scores[1] <= scores[2]
    assert scores[2] > scores[0]
    # Protection level escalates over turns
    assert levels[0] == ProtectionLevel.MONITORING
    assert levels[-1] in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]


# ==============================================================================
# Scenario 6: Duplicate Critical Events & Cooldown Behavior
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_duplicate_critical_events_cooldown():
    """Verify that repeated scam tactics within the cooldown window suppress duplicate alerts."""
    session_id = "e2e-cooldown-006"
    await create_test_session(session_id)
    pipeline = StreamingPipeline()

    scam_text = "This is Officer Smith from IRS. Give me your 6-digit OTP code right now to stop arrest."

    # Turn 1: Triggers fresh critical alert, caregiver SMS, user warning, and call disconnect
    seg1 = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text=scam_text,
        is_final=True,
        sequence_number=1,
    )
    res1 = await pipeline.process_segment(seg1)

    assert res1["protection"].cooldown_applied is False
    assert len(res1["notifications"]) == 1
    assert res1["notifications"][0].status == NotificationStatus.SENT
    assert res1["user_warning"] is not None
    assert res1["user_warning"].status == UserWarningStatus.DELIVERED
    assert res1["intervention"] is not None
    assert res1["intervention"].status == InterventionStatus.EXECUTED

    # Turn 2: Immediate non-escalating follow-up segment within 20s cooldown window
    seg2 = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="I repeat, your Social Security status is suspended. Please stay on the line.",
        is_final=True,
        sequence_number=2,
    )
    res2 = await pipeline.process_segment(seg2)

    # Cooldown suppresses duplicate dashboard alert, caregiver SMS, and user warning
    assert res2["protection"].cooldown_applied is True
    assert res2["notifications"] == []
    assert res2["user_warning"] is None
    # Idempotency suppresses duplicate call disconnect
    assert res2["intervention"] is None or res2["intervention"].status == InterventionStatus.SUPPRESSED


# ==============================================================================
# Scenario 7: Downstream Notification/Protection Failure Handling
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_downstream_notification_protection_failure():
    """Verify pipeline completes safely when downstream SMS, warning, or intervention services fail."""
    session_id = "e2e-failure-007"
    await create_test_session(session_id)
    pipeline = StreamingPipeline()

    # Configure all downstream providers to simulate network/delivery failure
    caregiver_notification_service.default_provider = MockSMSProvider(
        should_fail=True, fail_error="Simulated SMS gateway failure"
    )
    protected_user_warning_service.default_provider = MockUserWarningProvider(
        should_fail=True, fail_error="Simulated voice warning TTS failure"
    )
    intervention_service.default_provider = MockInterventionProvider(
        should_fail=True, fail_error="Simulated telephony API failure"
    )

    scam_text = "This is Federal Officer Brown. Wire $5,000 to our safe account immediately."
    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text=scam_text,
        is_final=True,
        sequence_number=1,
    )

    # Pipeline process_segment must NOT raise an exception
    result = await pipeline.process_segment(segment)

    # Classifier and Risk Engine results must be intact
    assert result["risk"].risk_tier in [RiskTier.MEDIUM, RiskTier.HIGH, RiskTier.CRITICAL]
    assert result["protection"].level in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]

    # Downstream failures recorded gracefully
    notifications = result["notifications"]
    assert len(notifications) == 1
    assert notifications[0].status == NotificationStatus.FAILED
    assert notifications[0].error == "Simulated SMS gateway failure"

    user_warning = result["user_warning"]
    assert user_warning is not None
    assert user_warning.status == UserWarningStatus.FAILED
    assert user_warning.error == "Simulated voice warning TTS failure"

    intervention = result["intervention"]
    assert intervention is not None
    assert intervention.status == InterventionStatus.FAILED
    assert intervention.error == "Simulated telephony API failure"


# ==============================================================================
# Scenario 8: Recovery After a Failure
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_recovery_after_failure():
    """Verify that after a downstream provider failure on Turn 1, Turn 2 recovers when provider is restored."""
    session_id = "e2e-recovery-008"
    await create_test_session(session_id)
    pipeline = StreamingPipeline()

    # Phase 1: Turn 1 with failing notification provider
    caregiver_notification_service.default_provider = MockSMSProvider(should_fail=True)

    seg1 = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="This is Officer Jones. We suspect fraudulent transactions on your account.",
        is_final=True,
        sequence_number=1,
    )
    res1 = await pipeline.process_segment(seg1)
    assert res1["notifications"][0].status == NotificationStatus.FAILED

    # Phase 2: Recovery - restore SMS provider and reset protection cooldown
    caregiver_notification_service.default_provider = MockSMSProvider(should_fail=False)
    protection_engine.reset_session(session_id)

    seg2 = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="Wire $5,000 to our government safety account right now to prevent arrest.",
        is_final=True,
        sequence_number=2,
    )
    res2 = await pipeline.process_segment(seg2)

    # Turn 2 successfully delivers caregiver notification
    assert len(res2["notifications"]) == 1
    assert res2["notifications"][0].status == NotificationStatus.SENT
    assert res2["intervention"] is not None
    assert res2["intervention"].status == InterventionStatus.EXECUTED
