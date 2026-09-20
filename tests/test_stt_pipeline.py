import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models import (
    ManipulationCategory,
    RiskTier,
    SpeakerType,
    TranscriptSegment,
    WSMessageType,
)
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.session_store import session_store
from backend.app.services.stt import DeepgramSTTProvider, MockSTTProvider
from ai.classifier import semantic_classifier


@pytest.fixture(scope="module", autouse=True)
def init_classifier():
    """Ensure semantic classifier is initialized for pipeline tests."""
    semantic_classifier.initialize()


# --- Test A: Mock STT Emits Transcript Segments in Order ---

@pytest.mark.asyncio
async def test_mock_stt_emits_in_order():
    """Verify MockSTTProvider emits segments in the exact order provided."""
    provider = MockSTTProvider()
    input_chunks = [
        "First utterance from caller.",
        "Second utterance with more details.",
        "Third final utterance.",
    ]

    emitted_segments = []
    async for segment in provider.stream_transcripts(
        session_id="session-test-order",
        input_data=input_chunks,
        speaker=SpeakerType.CALLER,
    ):
        emitted_segments.append(segment)

    assert len(emitted_segments) == 3
    for i, seg in enumerate(emitted_segments):
        assert seg.text == input_chunks[i]
        assert seg.session_id == "session-test-order"
        assert seg.speaker == SpeakerType.CALLER
        assert seg.is_final is True
        assert seg.timestamp > 0


# --- Test B & C: Segments Reach Classifier and Detected Tactics Reach Risk Engine ---

@pytest.mark.asyncio
async def test_transcript_reaches_classifier_and_risk_engine():
    """Verify transcript segment flows through classifier and risk engine in pipeline."""
    segment = TranscriptSegment(
        session_id="session-pipeline-flow",
        speaker=SpeakerType.CALLER,
        text="This is Officer Miller from the Federal Police Department.",
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)

    # B. Verified segment reached classifier
    assert len(result["matches"]) > 0
    tactics = [m.tactic for m in result["matches"]]
    assert ManipulationCategory.AUTHORITY_IMPERSONATION in tactics

    # C. Verified detected tactics reached risk engine
    assert result["risk"].overall_score > 0.0
    assert ManipulationCategory.AUTHORITY_IMPERSONATION in result["risk"].accumulated_tactics
    assert "AUTHORITY_IMPERSONATION" in result["risk"].explanation


# --- Test D: Risk Changes as Simulated Conversation Progresses ---

@pytest.mark.asyncio
async def test_risk_progression_in_simulation():
    """Verify risk increases dynamically across successive scam stages."""
    session_id = "session-scam-progression"
    scam_chunks = [
        "This is Officer Miller from the Federal Police Department.",
        "An arrest warrant has been issued in your name for criminal money laundering.",
        "You have only fifteen minutes to resolve this before officers arrive.",
        "Do not disconnect this line and do not tell your family about this call.",
        "Read me the six digit security code that was just sent to your phone.",
    ]

    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=scam_chunks,
        broadcast=False,
    )

    assert len(results) == 5

    # Check progressive escalation
    scores = [r["risk"].overall_score for r in results]
    # Stage 1 < Stage 2
    assert scores[0] < scores[1]
    # Stage 2 < Stage 3
    assert scores[1] < scores[2]
    # Final stage must reach CRITICAL (>= 90)
    assert scores[-1] >= 90.0
    assert results[-1]["risk"].risk_tier == RiskTier.CRITICAL


# --- Test E: Structured WebSocket Events Produced ---

@pytest.mark.asyncio
async def test_structured_streaming_events():
    """Verify TRANSCRIPT_UPDATE, TACTIC_DETECTED, RISK_UPDATE, and ALERT_TRIGGERED events."""
    session_id = "session-events-test"

    # Process critical scam segment directly
    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text=(
            "This is Officer Miller. An arrest warrant is active right now. "
            "Do not tell your family. Read me the six digit code immediately."
        ),
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)
    events = result["events"]
    event_types = [e.type for e in events]

    assert WSMessageType.TRANSCRIPT_UPDATE in event_types
    assert WSMessageType.TACTIC_DETECTED in event_types
    assert WSMessageType.RISK_UPDATE in event_types
    # Because this is a high-risk multi-tactic segment, ALERT_TRIGGERED should fire
    assert WSMessageType.ALERT_TRIGGERED in event_types

    # Validate ALERT_TRIGGERED payload
    alert_event = next(e for e in events if e.type == WSMessageType.ALERT_TRIGGERED)
    assert alert_event.data["session_id"] == session_id
    assert alert_event.data["overall_score"] >= 75.0
    assert len(alert_event.data["accumulated_tactics"]) > 0


# --- Test E2: WebSocket Integration with Simulated Stream ---

def test_websocket_integration_with_simulation():
    """Verify WebSocket client receives streaming events during a simulation."""
    client = TestClient(app)
    session_id = "session-ws-sim-test"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        # First message is SESSION_STATUS
        init_msg = websocket.receive_json()
        assert init_msg["type"] == WSMessageType.SESSION_STATUS.value

        # Trigger a single-utterance simulation via REST endpoint
        response = client.post(
            f"/api/sessions/{session_id}/simulate",
            json={
                "chunks": ["This is Officer Miller from the Federal Police Department."],
                "delay_seconds": 0.0,
            },
        )
        assert response.status_code == 200

        # Receive broadcasted events over WebSocket
        received_types = []
        for _ in range(3):  # TRANSCRIPT_UPDATE, TACTIC_DETECTED, RISK_UPDATE
            msg = websocket.receive_json()
            received_types.append(msg["type"])

        assert WSMessageType.TRANSCRIPT_UPDATE.value in received_types
        assert WSMessageType.TACTIC_DETECTED.value in received_types
        assert WSMessageType.RISK_UPDATE.value in received_types


# --- Test F: Neutral Transcript Does Not Generate High-Risk Alert ---

@pytest.mark.asyncio
async def test_neutral_transcript_no_alert():
    """Verify neutral conversation maintains 0.0 score and never emits ALERT_TRIGGERED."""
    session_id = "session-neutral-pipeline"
    neutral_chunks = [
        "Hey grandma, how are the tomatoes growing in your garden today?",
        "I baked some fresh cookies this afternoon with vanilla and cinnamon.",
        "Let me know if you would like me to bring some over tomorrow.",
    ]

    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=neutral_chunks,
        broadcast=False,
    )

    for r in results:
        assert r["risk"].overall_score == 0.0
        assert r["risk"].risk_tier == RiskTier.SAFE
        event_types = [e.type for e in r["events"]]
        assert WSMessageType.ALERT_TRIGGERED not in event_types


# --- Test H: Deepgram Provider Interface ---

def test_deepgram_provider_interface():
    """Verify DeepgramSTTProvider implements BaseSTTProvider interface and parameters."""
    deepgram = DeepgramSTTProvider(api_key="mock-key", sample_rate=8000, encoding="mulaw")
    assert deepgram.sample_rate == 8000
    assert deepgram.encoding == "mulaw"
    assert "mock-key" not in repr(deepgram)
    assert "***" in repr(deepgram)
