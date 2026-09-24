import asyncio
import pytest
from fastapi.testclient import TestClient

from ai.classifier import semantic_classifier
from backend.app.models import (
    CaregiverContact,
    InterventionStatus,
    NotificationStatus,
    ProtectionLevel,
    UserWarningStatus,
    WSMessageType,
)
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.session_store import session_store
from backend.app.services.notification_service import (
    MockSMSProvider,
    caregiver_notification_service,
)


@pytest.fixture(scope="module", autouse=True)
def init_classifier():
    """Ensure semantic classifier is initialized."""
    semantic_classifier.initialize()


INDIAN_SCAM_CHUNKS = [
    "This is Officer Sharma from the Cyber Crime Department.",
    "An arrest warrant and account freeze have been issued against your bank account for money laundering.",
    "You must resolve this urgent matter within fifteen minutes before police officers arrive at your residence.",
    "Do not disconnect this line and do not tell your family or anyone about this investigation.",
    "Read me the six digit OTP verification code that was just sent to your mobile phone.",
]


@pytest.mark.asyncio
async def test_alert_triggered_includes_caregiver_data():
    """Test A: ALERT_TRIGGERED includes real caregiver notification data when executed."""
    session_id = "test-bridge-caregiver-01"
    session = await session_store.create_session(
        session_id=session_id,
        callee_id="Lakshmi R.",
        caregiver_contacts=[
            CaregiverContact(
                name="Ananya R.",
                phone_number="+91 91234 56789",
                relationship="Daughter",
                enabled=True,
            )
        ],
    )

    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=INDIAN_SCAM_CHUNKS,
        broadcast=False,
    )

    # Locate the step where ALERT_TRIGGERED was emitted
    alert_events = [
        event
        for step in results
        for event in step["events"]
        if event.type == WSMessageType.ALERT_TRIGGERED
    ]
    assert len(alert_events) >= 1

    first_alert = alert_events[0]
    data = first_alert.data

    # Verify real caregiver notification payload
    assert "caregiver_notifications" in data
    assert isinstance(data["caregiver_notifications"], list)
    assert len(data["caregiver_notifications"]) == 1

    notif = data["caregiver_notifications"][0]
    assert notif["recipient"] == "+91 91234 56789"
    assert notif["status"] == NotificationStatus.SENT.value
    assert notif["provider"] == "mock"
    assert "notification_id" in notif
    assert notif["notification_id"] is not None
    assert "timestamp" in notif
    assert "Lakshmi R." in notif["message"]


@pytest.mark.asyncio
async def test_alert_triggered_includes_user_warning_data():
    """Test B: ALERT_TRIGGERED includes real user warning data when warning actually executes."""
    session_id = "test-bridge-warning-01"
    session = await session_store.create_session(
        session_id=session_id,
        callee_id="Lakshmi R.",
    )

    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=INDIAN_SCAM_CHUNKS,
        broadcast=False,
    )

    alert_events = [
        event
        for step in results
        for event in step["events"]
        if event.type == WSMessageType.ALERT_TRIGGERED
    ]
    assert len(alert_events) >= 1

    first_alert = alert_events[0]
    data = first_alert.data

    assert "user_warning" in data
    assert data["user_warning"] is not None
    warning = data["user_warning"]
    assert warning["status"] == UserWarningStatus.DELIVERED.value
    assert warning["provider"] == "mock"
    assert warning["channel"] == "VOICE"
    assert "warning_id" in warning
    assert warning["warning_id"] is not None
    assert len(warning["message"]) > 0


@pytest.mark.asyncio
async def test_alert_triggered_includes_intervention_data():
    """Test C: ALERT_TRIGGERED includes real intervention data when intervention actually executes."""
    session_id = "test-bridge-intervention-01"
    session = await session_store.create_session(
        session_id=session_id,
        callee_id="Lakshmi R.",
    )

    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=INDIAN_SCAM_CHUNKS,
        broadcast=False,
    )

    alert_events = [
        event
        for step in results
        for event in step["events"]
        if event.type == WSMessageType.ALERT_TRIGGERED
    ]
    assert len(alert_events) >= 1

    # Intervention executes on turn 3 or 5 where acute manipulation reaches critical
    intervention_alerts = [
        a for a in alert_events if a.data.get("intervention") is not None
    ]
    assert len(intervention_alerts) >= 1

    intervention = intervention_alerts[0].data["intervention"]
    assert intervention["status"] == InterventionStatus.EXECUTED.value
    assert intervention["provider"] == "mock"
    assert intervention["type"] == "DISCONNECT"
    assert "intervention_id" in intervention
    assert intervention["intervention_id"] is not None


@pytest.mark.asyncio
async def test_missing_downstream_actions_safe_representation():
    """Test D: Missing downstream actions are represented safely and do not crash."""
    session_id = "test-bridge-missing-actions-01"
    # Session without caregivers
    session = await session_store.create_session(session_id=session_id)

    # Process a single high-threat segment
    segment_text = "This is the police and an arrest warrant has been issued against you immediately."
    async for segment in streaming_pipeline.mock_stt.stream_transcripts(
        session_id=session_id,
        input_data=[segment_text],
        delay_seconds=0.0,
    ):
        result = await streaming_pipeline.process_segment(segment, broadcast=False)

    for event in result["events"]:
        if event.type == WSMessageType.ALERT_TRIGGERED:
            # Caregiver notifications must be empty list, NOT missing or None
            assert event.data["caregiver_notifications"] == []
            # When intervention is not triggered, it must be None
            if not result.get("intervention"):
                assert event.data["intervention"] is None


@pytest.mark.asyncio
async def test_generic_sessions_no_fake_caregivers():
    """Test E: Generic sessions without caregivers do not receive fake caregiver notifications."""
    session_id = "test-bridge-generic-no-caregiver"
    session = await session_store.create_session(session_id=session_id)
    assert session.caregiver_contacts == []

    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=INDIAN_SCAM_CHUNKS,
        broadcast=False,
    )

    for step in results:
        for event in step["events"]:
            if event.type == WSMessageType.ALERT_TRIGGERED:
                assert event.data["caregiver_notifications"] == []

    # Verify session store notification history is completely empty
    refreshed_session = await session_store.get_session(session_id)
    assert len(refreshed_session.notification_history) == 0


def test_websocket_event_order_unchanged(client: TestClient):
    """Test F: Existing WebSocket event order remains unchanged (exactly 4 events)."""
    session_id = "test-bridge-event-order"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        # Drain initial SESSION_STATUS
        init_msg = websocket.receive_json()
        assert init_msg["type"] == WSMessageType.SESSION_STATUS.value

        # Post Indian scam chunks via simulate endpoint
        resp = client.post(
            f"/api/sessions/{session_id}/simulate",
            json={
                "chunks": [INDIAN_SCAM_CHUNKS[0], INDIAN_SCAM_CHUNKS[1], INDIAN_SCAM_CHUNKS[2]],
                "delay_seconds": 0.0,
                "caregiver_contacts": [
                    {
                        "name": "Ananya R.",
                        "phone_number": "+91 91234 56789",
                        "relationship": "Daughter",
                        "enabled": True,
                    }
                ],
            },
        )
        assert resp.status_code == 200

        # Collect event types received for turn 3 (where ALERT_TRIGGERED fires)
        received_types = []
        # Receive events for all 3 turns
        while True:
            try:
                msg = websocket.receive_json()
                received_types.append(msg["type"])
                if msg["type"] == WSMessageType.ALERT_TRIGGERED.value:
                    # Check the immediate 4 events leading to and including this alert
                    last_four = received_types[-4:]
                    assert last_four == [
                        WSMessageType.TRANSCRIPT_UPDATE.value,
                        WSMessageType.TACTIC_DETECTED.value,
                        WSMessageType.RISK_UPDATE.value,
                        WSMessageType.ALERT_TRIGGERED.value,
                    ]
                    # Verify payload has enriched fields
                    assert "caregiver_notifications" in msg["data"]
                    assert "user_warning" in msg["data"]
                    assert "intervention" in msg["data"]
                    break
            except Exception:
                break


@pytest.mark.asyncio
async def test_new_session_reset_isolation():
    """Test G: New session does not leak previous protection state."""
    # 1. Run session 1 to completion with caregiver
    session_1_id = "test-bridge-isolation-s1"
    session_1 = await session_store.create_session(
        session_id=session_1_id,
        callee_id="Lakshmi R.",
        caregiver_contacts=[
            CaregiverContact(name="Ananya R.", phone_number="+91 91234 56789")
        ],
    )

    await streaming_pipeline.run_simulation(
        session_id=session_1_id,
        chunks=INDIAN_SCAM_CHUNKS,
        broadcast=False,
    )

    refreshed_1 = await session_store.get_session(session_1_id)
    assert len(refreshed_1.notification_history) > 0
    assert len(refreshed_1.user_warning_history) > 0

    # 2. Create fresh session 2 (simulating reset)
    session_2_id = "test-bridge-isolation-s2"
    session_2 = await session_store.create_session(session_id=session_2_id)

    assert session_2.caregiver_contacts == []
    assert session_2.notification_history == []
    assert session_2.user_warning_history == []
    assert session_2.intervention_history == []
    assert session_2.protection_history == []


@pytest.mark.asyncio
async def test_downstream_failure_isolation():
    """Test H: Downstream caregiver delivery failure marks FAILED without corrupting other actions or risk."""
    session_id = "test-bridge-failure-isolation"
    session = await session_store.create_session(
        session_id=session_id,
        callee_id="Lakshmi R.",
        caregiver_contacts=[
            CaregiverContact(name="Ananya R.", phone_number="+91 91234 56789")
        ],
    )

    orig_provider = caregiver_notification_service.default_provider
    try:
        caregiver_notification_service.default_provider = MockSMSProvider(should_fail=True)
        results = await streaming_pipeline.run_simulation(
            session_id=session_id,
            chunks=INDIAN_SCAM_CHUNKS,
            broadcast=False,
        )

        alert_events = [
            event
            for step in results
            for event in step["events"]
            if event.type == WSMessageType.ALERT_TRIGGERED
        ]
        assert len(alert_events) >= 1
        first_alert = alert_events[0]
        data = first_alert.data

        # Caregiver failure must be explicitly FAILED, never SENT
        assert len(data["caregiver_notifications"]) == 1
        caregiver_record = data["caregiver_notifications"][0]
        assert caregiver_record["status"] == NotificationStatus.FAILED.value
        assert caregiver_record["status"] != NotificationStatus.SENT.value
        assert "Simulated SMS delivery failure" in (caregiver_record["error"] or "")

        # Downstream user warning must still succeed
        assert data["user_warning"] is not None
        assert data["user_warning"]["status"] == UserWarningStatus.DELIVERED.value

        # Threat/risk score must not be corrupted
        assert data["overall_score"] > 0.0
    finally:
        caregiver_notification_service.default_provider = orig_provider
