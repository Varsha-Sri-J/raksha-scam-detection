import time
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models import (
    CallSession,
    CaregiverContact,
    NotificationChannel,
    NotificationRecord,
    NotificationStatus,
    ProtectionAction,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    ProtectionLevel,
    RiskAssessment,
    RiskTier,
    SpeakerType,
    TranscriptSegment,
    WSMessageType,
)
from backend.app.services.notification_service import (
    CaregiverNotificationService,
    MockSMSProvider,
    caregiver_notification_service,
)
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.protection_engine import protection_engine
from backend.app.services.session_store import session_store
from ai.classifier import semantic_classifier


@pytest.fixture(autouse=True)
def cleanup_state():
    """Reset protection engine and notification provider before and after each test."""
    protection_engine.clear()
    caregiver_notification_service.default_provider = MockSMSProvider()
    yield
    protection_engine.clear()
    caregiver_notification_service.default_provider = MockSMSProvider()


# Helper to construct a test session with caregiver contacts
def make_test_session(session_id: str, contacts=None) -> CallSession:
    if contacts is None:
        contacts = [
            CaregiverContact(name="Alice Doe", phone_number="+18005550111", enabled=True),
        ]
    return CallSession(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="Margaret H.",
        caregiver_contacts=contacts,
    )


# Helper to construct a test ProtectionDecision
def make_decision(
    session_id: str,
    level: ProtectionLevel,
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


# --- 1. Caregiver model defaults ---
def test_caregiver_model_defaults():
    contact = CaregiverContact(name="John Doe", phone_number="+15551234567")
    assert contact.name == "John Doe"
    assert contact.phone_number == "+15551234567"
    assert contact.enabled is True

    # CallSession defaults
    session = CallSession()
    assert isinstance(session.caregiver_contacts, list)
    assert len(session.caregiver_contacts) == 0
    assert isinstance(session.notification_history, list)
    assert len(session.notification_history) == 0


# --- 2. Session caregiver isolation ---
def test_session_caregiver_isolation():
    session_a = CallSession(
        session_id="session-a",
        caregiver_contacts=[CaregiverContact(name="Contact A", phone_number="+15550000001")],
    )
    session_b = CallSession(session_id="session-b")

    # Modifying session_a contacts must not affect session_b
    assert len(session_a.caregiver_contacts) == 1
    assert len(session_b.caregiver_contacts) == 0
    session_b.caregiver_contacts.append(
        CaregiverContact(name="Contact B", phone_number="+15550000002")
    )
    assert len(session_a.caregiver_contacts) == 1
    assert len(session_b.caregiver_contacts) == 1
    assert session_a.caregiver_contacts[0].name == "Contact A"
    assert session_b.caregiver_contacts[0].name == "Contact B"


# --- 3. Mock SMS success ---
def test_mock_sms_success():
    provider = MockSMSProvider()
    result = provider.send_sms("+15550001111", "Test message")

    assert result.success is True
    assert result.provider == "mock"
    assert result.message_id is not None
    assert result.message_id.startswith("mock-sms-")
    assert result.error is None
    assert len(provider.sent_messages) == 1
    assert provider.sent_messages[0]["recipient"] == "+15550001111"


# --- 4. Mock SMS failure ---
def test_mock_sms_failure():
    provider = MockSMSProvider(should_fail=True, fail_error="Simulated network error")
    result = provider.send_sms("+15550002222", "Test failure message")

    assert result.success is False
    assert result.provider == "mock"
    assert result.error == "Simulated network error"
    assert result.message_id is None
    assert len(provider.sent_messages) == 0


# --- 5. MEDIUM does not notify caregiver ---
def test_medium_tier_does_not_notify_caregiver():
    service = CaregiverNotificationService()
    session = make_test_session("session-med")
    decision = make_decision("session-med", level=ProtectionLevel.ADVISORY, has_dashboard_alert=False, score=60.0, tier=RiskTier.MEDIUM)

    records = service.dispatch_notifications(session, decision)
    assert len(records) == 0


# --- 6. First HIGH protection alert triggers caregiver notification ---
def test_first_high_protection_alert_triggers_notification():
    provider = MockSMSProvider()
    service = CaregiverNotificationService(default_provider=provider)
    session = make_test_session("session-high")
    decision = make_decision("session-high", level=ProtectionLevel.WARNING, has_dashboard_alert=True, score=78.0, tier=RiskTier.HIGH)

    records = service.dispatch_notifications(session, decision)
    assert len(records) == 1
    rec = records[0]
    assert rec.status == NotificationStatus.SENT
    assert rec.channel == NotificationChannel.SMS
    assert rec.recipient == "+18005550111"
    assert "RAKSHA ALERT" in rec.message
    assert "HIGH" in rec.message
    assert rec.error is None
    assert len(provider.sent_messages) == 1


# --- 7. CRITICAL protection alert triggers caregiver notification ---
def test_critical_protection_alert_triggers_notification():
    provider = MockSMSProvider()
    service = CaregiverNotificationService(default_provider=provider)
    session = make_test_session("session-crit")
    decision = make_decision("session-crit", level=ProtectionLevel.CRITICAL_INTERCEPT, has_dashboard_alert=True, score=95.0, tier=RiskTier.CRITICAL)

    records = service.dispatch_notifications(session, decision)
    assert len(records) == 1
    rec = records[0]
    assert rec.status == NotificationStatus.SENT
    assert "CRITICAL ALERT" in rec.message
    assert "CRITICAL" in rec.message
    assert "immediately" in rec.message


# --- 8. Cooldown-suppressed HIGH does NOT notify caregiver ---
def test_cooldown_suppressed_high_does_not_notify_caregiver():
    provider = MockSMSProvider()
    service = CaregiverNotificationService(default_provider=provider)
    session = make_test_session("session-cooldown")

    # Suppose cooldown suppressed the alert -> has_dashboard_alert = False
    decision = make_decision("session-cooldown", level=ProtectionLevel.WARNING, has_dashboard_alert=False, score=80.0, tier=RiskTier.HIGH)

    records = service.dispatch_notifications(session, decision)
    assert len(records) == 0
    assert len(provider.sent_messages) == 0


# --- 9. Session isolation in notification dispatch ---
def test_session_isolation_in_dispatch():
    provider = MockSMSProvider()
    service = CaregiverNotificationService(default_provider=provider)

    session_1 = make_test_session("session-1", contacts=[CaregiverContact(name="C1", phone_number="+1111")])
    session_2 = make_test_session("session-2", contacts=[CaregiverContact(name="C2", phone_number="+2222")])

    d1 = make_decision("session-1", level=ProtectionLevel.WARNING, has_dashboard_alert=True)
    d2 = make_decision("session-2", level=ProtectionLevel.WARNING, has_dashboard_alert=False)

    r1 = service.dispatch_notifications(session_1, d1)
    r2 = service.dispatch_notifications(session_2, d2)

    assert len(r1) == 1
    assert r1[0].recipient == "+1111"
    assert len(r2) == 0
    assert len(provider.sent_messages) == 1


# --- 10. Notification history recording in SessionStore ---
@pytest.mark.asyncio
async def test_notification_history_recording_in_session_store():
    session = await session_store.create_session(session_id="test-store-notif-01")
    assert len(session.notification_history) == 0

    record = NotificationRecord(
        session_id="test-store-notif-01",
        channel=NotificationChannel.SMS,
        recipient="+18005550111",
        message="Test alert message",
        status=NotificationStatus.SENT,
    )

    await session_store.add_notification_record("test-store-notif-01", record)
    retrieved = await session_store.get_session("test-store-notif-01")
    assert retrieved is not None
    assert len(retrieved.notification_history) == 1
    assert retrieved.notification_history[0].recipient == "+18005550111"
    assert retrieved.notification_history[0].status == NotificationStatus.SENT


# --- 11. History bounded to 100 in SessionStore ---
@pytest.mark.asyncio
async def test_notification_history_bounded_to_100():
    session_id = "test-store-bounded-notif"
    await session_store.create_session(session_id=session_id)

    for i in range(110):
        rec = NotificationRecord(
            session_id=session_id,
            channel=NotificationChannel.SMS,
            recipient=f"+1800555{i:04d}",
            message=f"Message {i}",
            status=NotificationStatus.SENT,
        )
        await session_store.add_notification_record(session_id, rec)

    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.notification_history) == 100
    # Last record should be message 109
    assert session.notification_history[-1].recipient == "+18005550109"


# --- 12. Notification failure does not break pipeline ---
@pytest.mark.asyncio
async def test_notification_failure_does_not_break_pipeline():
    """Verify that when SMS provider fails, pipeline continues smoothly and records failure."""
    semantic_classifier.initialize()
    failing_provider = MockSMSProvider(should_fail=True, fail_error="Simulated carrier down")
    caregiver_notification_service.default_provider = failing_provider

    session_id = "test-pipeline-notif-fail"
    session = await session_store.create_session(
        session_id=session_id,
        caller_id="+18005550199",
        callee_id="Protected Callee",
    )
    session.caregiver_contacts = [
        CaregiverContact(name="Emergency Caregiver", phone_number="+18005550999", enabled=True)
    ]

    # Critical utterance that triggers alert
    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="This is Officer Miller from the Police. An arrest warrant has been issued. Give me your 6 digit code right now.",
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)

    # Pipeline succeeded
    assert result["risk"].overall_score >= 75.0
    assert result["protection"] is not None

    # Notification was attempted and recorded as FAILED
    updated_session = await session_store.get_session(session_id)
    assert updated_session is not None
    assert len(updated_session.notification_history) == 1
    failed_record = updated_session.notification_history[0]
    assert failed_record.status == NotificationStatus.FAILED
    assert "Simulated carrier down" in failed_record.error


# --- 13. Existing ALERT_TRIGGERED event order preserved ---
def test_ws_event_order_preserved_with_caregiver_notifications(client: TestClient):
    """Verify WebSocket emits events in exact order with caregiver notifications active."""
    semantic_classifier.initialize()
    session_id = "test-ws-caregiver-order"

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

        # Event 4: ALERT_TRIGGERED
        e4 = websocket.receive_json()
        assert e4["type"] == WSMessageType.ALERT_TRIGGERED.value
        assert e4["data"]["session_id"] == session_id


# --- 14. No external network calls (Mock provider verification) ---
def test_no_external_network_calls():
    provider = MockSMSProvider()
    res = provider.send_sms("+18005550000", "Zero network call test")
    assert res.success is True
    assert res.provider == "mock"


# --- 15. Existing mock simulation still works ---
@pytest.mark.asyncio
async def test_mock_simulation_with_caregiver_service():
    """Verify mock STT simulation continues to function with caregiver service integrated."""
    session_id = "test-sim-caregiver-pipeline"
    session = await session_store.create_session(session_id=session_id)
    session.caregiver_contacts = [
        CaregiverContact(name="Family Contact", phone_number="+18005550888", enabled=True)
    ]

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
    updated_session = await session_store.get_session(session_id)
    assert updated_session is not None
    # Caregiver notification was triggered for qualifying high/critical steps
    assert len(updated_session.notification_history) >= 1
    assert updated_session.notification_history[0].status == NotificationStatus.SENT
