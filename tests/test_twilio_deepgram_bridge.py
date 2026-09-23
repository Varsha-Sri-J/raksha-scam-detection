import asyncio
import base64
import json
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ai.classifier import semantic_classifier
from backend.app.config import settings
from backend.app.main import app
from backend.app.models import (
    ManipulationCategory,
    RiskTier,
    SpeakerType,
    TranscriptSegment,
    WSMessageType,
)
from backend.app.services.connection_manager import manager
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.session_store import session_store
from backend.app.services.stt import DeepgramSTTProvider, MockSTTProvider, get_stt_provider
from backend.app.services.twilio_service import twilio_service


@pytest.fixture(scope="module", autouse=True)
def init_classifier():
    """Ensure semantic classifier is initialized for bridge tests."""
    semantic_classifier.initialize()


# --- Test 1: Queue → Async Generator Behavior ---

@pytest.mark.asyncio
async def test_audio_queue_to_async_generator_behavior():
    """Verify that an asyncio.Queue feeds an async generator sequentially and terminates on EOF sentinel."""
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=500)

    async def audio_stream_generator():
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    # Enqueue chunks and EOF sentinel
    chunks = [b"chunk_1", b"chunk_2", b"chunk_3"]
    for c in chunks:
        queue.put_nowait(c)
    queue.put_nowait(None)

    consumed = []
    async for item in audio_stream_generator():
        consumed.append(item)

    assert consumed == chunks
    assert queue.empty()


# --- Test 2: Twilio Media Payload → Decoded Bytes ---

def test_twilio_media_payload_decoding():
    """Verify TwilioService safely decodes valid base64 audio and rejects malformed payloads."""
    raw_audio = b"\xff\xaa\x55\x10" * 40
    valid_b64 = base64.b64encode(raw_audio).decode("utf-8")

    # Valid payload
    decoded = twilio_service.decode_media_payload(valid_b64)
    assert decoded == raw_audio

    # Invalid / corrupt base64
    assert twilio_service.decode_media_payload("!!!not_base64@@@") is None
    # Empty or non-string
    assert twilio_service.decode_media_payload("") is None
    assert twilio_service.decode_media_payload(None) is None


# --- Test 3: Decoded Bytes Reaching EXISTING DeepgramSTTProvider Interface ---

@pytest.mark.asyncio
async def test_decoded_bytes_reaching_existing_deepgram_interface():
    """Verify DeepgramSTTProvider accepts an async generator of decoded bytes as input_data."""
    provider = DeepgramSTTProvider(api_key="mock-test-key")

    mock_ws = AsyncMock()

    async def mock_ws_iter():
        yield json.dumps({
            "is_final": True,
            "start": 1.0,
            "channel": {
                "alternatives": [{"transcript": "Verification call from your bank.", "confidence": 0.95}]
            },
        })

    mock_ws.__aiter__.side_effect = mock_ws_iter

    mock_connect = AsyncMock()
    mock_connect.__aenter__.return_value = mock_ws
    mock_connect.__aexit__.return_value = None

    async def test_audio_generator():
        yield b"\x01\x02\x03\x04"
        yield b"\x05\x06\x07\x08"

    with patch("websockets.connect", return_value=mock_connect):
        segments = []
        async for seg in provider.stream_transcripts(
            session_id="session-existing-interface",
            input_data=test_audio_generator(),
            speaker=SpeakerType.CALLER,
        ):
            segments.append(seg)

        assert len(segments) == 1
        assert segments[0].text == "Verification call from your bank."
        assert segments[0].speaker == SpeakerType.CALLER
        assert segments[0].session_id == "session-existing-interface"


# --- Test 4: Mocked Deepgram WebSocket Receiving Expected Audio Bytes ---

@pytest.mark.asyncio
async def test_mocked_deepgram_websocket_receives_audio_bytes_and_close():
    """Verify Deepgram WebSocket receives each audio frame in order followed by CloseStream."""
    provider = DeepgramSTTProvider(api_key="mock-test-key")

    sent_messages = []
    mock_ws = AsyncMock()

    async def mock_send(msg):
        sent_messages.append(msg)

    mock_ws.send.side_effect = mock_send

    async def mock_ws_iter():
        # Allow sender task to complete
        await asyncio.sleep(0.01)
        return
        yield

    mock_ws.__aiter__.side_effect = mock_ws_iter

    mock_connect = AsyncMock()
    mock_connect.__aenter__.return_value = mock_ws
    mock_connect.__aexit__.return_value = None

    test_frames = [b"\xaa\xbb\xcc", b"\xdd\xee\xff"]

    async def frame_generator():
        for f in test_frames:
            yield f

    with patch("websockets.connect", return_value=mock_connect):
        async for _ in provider.stream_transcripts(
            session_id="session-ws-bytes",
            input_data=frame_generator(),
        ):
            pass

    # Verify sent messages: audio frames then CloseStream
    assert test_frames[0] in sent_messages
    assert test_frames[1] in sent_messages
    close_stream_found = any(
        isinstance(m, str) and json.loads(m).get("type") == "CloseStream"
        for m in sent_messages
    )
    assert close_stream_found is True


# --- Test 5: Mocked Deepgram Transcript Response Producing TranscriptSegment ---

def test_mocked_deepgram_transcript_response_produces_segment():
    """Verify DeepgramSTTProvider.parse_deepgram_response transforms Deepgram JSON to TranscriptSegment."""
    payload = {
        "is_final": True,
        "start": 2.45,
        "channel": {
            "alternatives": [
                {
                    "transcript": "This is Officer Miller from the Federal Police Department.",
                    "confidence": 0.98,
                }
            ]
        },
    }

    segment = DeepgramSTTProvider.parse_deepgram_response(
        payload, session_id="session-parse-test", speaker=SpeakerType.CALLER
    )

    assert segment is not None
    assert segment.session_id == "session-parse-test"
    assert segment.speaker == SpeakerType.CALLER
    assert segment.text == "This is Officer Miller from the Federal Police Department."
    assert segment.timestamp == 2.45
    assert segment.is_final is True


# --- Test 6: TranscriptSegment Reaching StreamingPipeline ---

@pytest.mark.asyncio
async def test_transcript_segment_reaching_streaming_pipeline():
    """Verify TranscriptSegment flows into StreamingPipeline, triggers classifier, and updates risk."""
    session_id = "session-pipeline-integration"
    await session_store.create_session(session_id=session_id)

    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text="An arrest warrant has been issued in your name for criminal money laundering.",
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)

    assert "matches" in result
    assert "risk" in result
    assert len(result["matches"]) > 0
    assert result["risk"].overall_score > 0.0

    # Verify session store was updated
    session = await session_store.get_session(session_id)
    assert session is not None
    assert len(session.transcript_history) == 1
    assert session.latest_risk.overall_score == result["risk"].overall_score


# --- Test 7: Dashboard Events Emitted ---

@pytest.mark.asyncio
async def test_dashboard_events_emitted_during_pipeline():
    """Verify pipeline emits TRANSCRIPT_UPDATE, TACTIC_DETECTED, RISK_UPDATE, and ALERT_TRIGGERED."""
    session_id = "session-dashboard-events"
    await session_store.create_session(session_id=session_id)

    # Multi-tactic scam segment to trigger ALERT_TRIGGERED
    segment = TranscriptSegment(
        session_id=session_id,
        speaker=SpeakerType.CALLER,
        text=(
            "This is Officer Miller. An arrest warrant is active right now. "
            "Do not tell your family. Read me the six digit code immediately."
        ),
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)
    event_types = [e.type for e in result["events"]]

    assert WSMessageType.TRANSCRIPT_UPDATE in event_types
    assert WSMessageType.TACTIC_DETECTED in event_types
    assert WSMessageType.RISK_UPDATE in event_types
    assert WSMessageType.ALERT_TRIGGERED in event_types


# --- Test 8: Queue Overflow Behavior ---

def test_queue_overflow_behavior(client: TestClient):
    """Verify bounded queue (maxsize=500) drops newest frames without blocking or unbounded memory."""
    session_id = "CA-test-queue-overflow"
    dummy_payload = base64.b64encode(b"\x00\x01\x02\x03" * 20).decode("utf-8")

    # Connect to media stream
    with client.websocket_connect(f"/ws/twilio/media/{session_id}") as ws:
        ws.send_json({"event": "connected", "protocol": "Call"})
        ws.send_json({
            "event": "start",
            "start": {"streamSid": "MZ-overflow-test", "callSid": session_id},
        })

        # Send 550 media frames (exceeding queue maxsize of 500)
        for i in range(550):
            ws.send_json({
                "event": "media",
                "sequenceNumber": str(i + 1),
                "media": {
                    "track": "inbound",
                    "chunk": str(i + 1),
                    "timestamp": str(1000 + i),
                    "payload": dummy_payload,
                },
            })

        # Send stop to cleanly exit
        ws.send_json({"event": "stop"})

    # Check session exists and is healthy
    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200


# --- Test 9: Malformed / Corrupt Media Handling ---

def test_malformed_and_corrupt_media(client: TestClient):
    """Verify malformed JSON or invalid base64 media does not crash the WebSocket or bridge."""
    session_id = "CA-test-corrupt-media"

    with client.websocket_connect(f"/ws/twilio/media/{session_id}") as ws:
        ws.send_json({"event": "connected"})
        ws.send_json({"event": "start", "start": {"streamSid": "MZ-corrupt", "callSid": session_id}})

        # 1. Invalid base64 in media payload
        ws.send_json({
            "event": "media",
            "media": {"track": "inbound", "payload": "!!!not_valid_base64@@@"},
        })

        # 2. Unsupported track (outbound)
        ws.send_json({
            "event": "media",
            "media": {
                "track": "outbound",
                "payload": base64.b64encode(b"\x00" * 40).decode("utf-8"),
            },
        })

        # 3. Completely non-dictionary text
        ws.send_text("THIS IS NOT JSON")

        # 4. Valid media frame after errors to verify bridge is still functioning
        valid_b64 = base64.b64encode(b"\xaa\xbb\xcc\xdd" * 20).decode("utf-8")
        ws.send_json({
            "event": "media",
            "media": {"track": "inbound", "payload": valid_b64},
        })

        # Clean stop
        ws.send_json({"event": "stop"})


# --- Test 10 & 11: Deepgram Failure Lifecycle & Audio Consumer Safety ---

def test_deepgram_failure_broadcasts_error_and_stops_consumer(client: TestClient):
    """Verify Deepgram failure emits WS ERROR event, marks STT failed, stops queueing audio, and preserves Twilio WS."""
    session_id = "CA-test-deepgram-failure"

    class FailingSTTProvider:
        async def stream_transcripts(self, *args, **kwargs):
            raise ConnectionError("Deepgram service unavailable: connection refused")
            yield  # pragma: no cover

    with patch("backend.app.main.get_stt_provider", return_value=FailingSTTProvider()):
        # Connect dashboard client to receive WS error broadcast
        with client.websocket_connect(f"/ws/call/{session_id}") as dash_ws:
            # First message on connect is SESSION_STATUS
            init_msg = dash_ws.receive_json()
            assert init_msg["type"] == WSMessageType.SESSION_STATUS.value

            # Connect Twilio Media Stream
            with client.websocket_connect(f"/ws/twilio/media/{session_id}") as twilio_ws:
                twilio_ws.send_json({"event": "connected"})
                twilio_ws.send_json({"event": "start", "start": {"streamSid": "MZ-fail", "callSid": session_id}})

                # Send media to trigger STT worker failure
                dummy_payload = base64.b64encode(b"\x00\x01\x02\x03" * 20).decode("utf-8")
                twilio_ws.send_json({
                    "event": "media",
                    "media": {"track": "inbound", "payload": dummy_payload},
                })

                # Receive ERROR event on dashboard WS
                error_msg = dash_ws.receive_json()
                assert error_msg["type"] == WSMessageType.ERROR.value
                assert "STT bridge error" in error_msg["data"]["error"]

                # Subsequent media frames should NOT crash the Twilio WS (consumer safely stopped)
                for _ in range(5):
                    twilio_ws.send_json({
                        "event": "media",
                        "media": {"track": "inbound", "payload": dummy_payload},
                    })

                # Twilio WS is still alive and responds to stop cleanly
                twilio_ws.send_json({"event": "stop"})


# --- Test 12: Twilio Stop Cleanup ---

def test_twilio_stop_cleanup(client: TestClient):
    """Verify 'stop' event triggers graceful shutdown of STT worker without timing out."""
    session_id = "CA-test-stop-cleanup"

    with client.websocket_connect(f"/ws/twilio/media/{session_id}") as ws:
        ws.send_json({"event": "connected"})
        ws.send_json({"event": "start", "start": {"streamSid": "MZ-stop", "callSid": session_id}})
        ws.send_json({"event": "stop"})

    # Session remains active and accessible
    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200


# --- Test 13: Abrupt Twilio Disconnect Cleanup ---

def test_abrupt_twilio_disconnect_cleanup(client: TestClient):
    """Verify abrupt client disconnect terminates STT worker safely in finally block."""
    session_id = "CA-test-abrupt-disconnect"

    # Open and immediately close without sending "stop"
    with client.websocket_connect(f"/ws/twilio/media/{session_id}") as ws:
        ws.send_json({"event": "connected"})
        dummy_payload = base64.b64encode(b"\x00\x01" * 20).decode("utf-8")
        ws.send_json({
            "event": "media",
            "media": {"track": "inbound", "payload": dummy_payload},
        })
        # Context manager exit triggers WebSocket close / disconnect

    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200


# --- Test 14: No Orphaned STT Tasks ---

@pytest.mark.asyncio
async def test_no_orphaned_stt_tasks():
    """Verify that after normal stop or abrupt disconnect, no STT tasks remain running."""
    session_id = "CA-test-no-orphans"
    client = TestClient(app)

    tasks_before = [t for t in asyncio.all_tasks() if not t.done()]

    with client.websocket_connect(f"/ws/twilio/media/{session_id}") as ws:
        ws.send_json({"event": "connected"})
        ws.send_json({"event": "start", "start": {"streamSid": "MZ-orphan", "callSid": session_id}})
        dummy_payload = base64.b64encode(b"\x00\x01\x02\x03" * 20).decode("utf-8")
        ws.send_json({
            "event": "media",
            "media": {"track": "inbound", "payload": dummy_payload},
        })
        ws.send_json({"event": "stop"})

    # Allow any cleanup microtasks to settle
    await asyncio.sleep(0.05)

    tasks_after = [t for t in asyncio.all_tasks() if not t.done()]
    # Ensure no stt worker task is in tasks_after that wasn't in tasks_before
    active_stt_tasks = [
        t for t in tasks_after
        if "run_stt_worker" in str(t.get_coro())
    ]
    assert len(active_stt_tasks) == 0


# --- Test 15: Mock Mode Regression ---

def test_mock_mode_regression_and_bridge_integration(client: TestClient):
    """Verify that in default STT_PROVIDER=mock mode, Twilio media stream produces simulated scam segments and events."""
    session_id = "CA-test-mock-mode-regression"

    with client:
        # 1. Connect dashboard client to observe live events
        with client.websocket_connect(f"/ws/call/{session_id}") as dash_ws:
            init_msg = dash_ws.receive_json()
            assert init_msg["type"] == WSMessageType.SESSION_STATUS.value

            # 2. Connect Twilio Media Stream
            with client.websocket_connect(f"/ws/twilio/media/{session_id}") as twilio_ws:
                twilio_ws.send_json({"event": "connected"})
                twilio_ws.send_json({"event": "start", "start": {"streamSid": "MZ-mock-reg", "callSid": session_id}})

                # Send a media frame — MockSTTProvider will consume it and emit the first scam chunk
                dummy_payload = base64.b64encode(b"\x00\x01\x02\x03" * 20).decode("utf-8")
                twilio_ws.send_json({
                    "event": "media",
                    "media": {"track": "inbound", "payload": dummy_payload},
                })

                # Dashboard should receive TRANSCRIPT_UPDATE, TACTIC_DETECTED, RISK_UPDATE
                events_received = []
                for _ in range(3):
                    msg = dash_ws.receive_json()
                    events_received.append(msg["type"])

                assert WSMessageType.TRANSCRIPT_UPDATE.value in events_received
                assert WSMessageType.TACTIC_DETECTED.value in events_received
                assert WSMessageType.RISK_UPDATE.value in events_received

                # Send stop to cleanly complete the media stream and worker
                twilio_ws.send_json({"event": "stop"})

    # 3. Verify REST simulation endpoint still works unchanged
    sim_resp = client.post(
        f"/api/sessions/{session_id}/simulate",
        json={
            "chunks": ["Please do not tell anyone about this conversation."],
            "delay_seconds": 0.0,
        },
    )
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    assert sim_data["steps_processed"] == 1
    assert len(sim_data["summary"]) == 1
