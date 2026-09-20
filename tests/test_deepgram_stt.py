import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest

from backend.app.config import settings
from backend.app.models import SpeakerType, TranscriptSegment
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.stt import (
    DeepgramSTTProvider,
    MockSTTProvider,
    get_stt_provider,
)


# --- Test A: Mock Provider Works With No API Key ---

@pytest.mark.asyncio
async def test_mock_provider_works_with_no_api_key():
    """Verify MockSTTProvider functions properly without any Deepgram API key."""
    provider = MockSTTProvider()
    chunks = ["Hello, this is a test utterance."]

    emitted = []
    async for segment in provider.stream_transcripts(
        session_id="session-mock-no-key",
        input_data=chunks,
    ):
        emitted.append(segment)

    assert len(emitted) == 1
    assert emitted[0].text == "Hello, this is a test utterance."
    assert emitted[0].is_final is True


# --- Test B: STT Provider Selection Chooses Mock by Default ---

def test_stt_provider_selection_chooses_mock_by_default():
    """Verify get_stt_provider() defaults to MockSTTProvider when no key is set."""
    with patch.object(settings, "DEEPGRAM_API_KEY", None):
        with patch.object(settings, "STT_PROVIDER", "mock"):
            provider = get_stt_provider()
            assert isinstance(provider, MockSTTProvider)


# --- Test C: Deepgram Provider Instantiation Masks API Key ---

def test_deepgram_provider_instantiation_masks_key():
    """Verify DeepgramSTTProvider masks credentials in string/repr output."""
    raw_key = "secret-deepgram-api-key-9999"
    provider = DeepgramSTTProvider(api_key=raw_key)

    repr_str = repr(provider)
    assert raw_key not in repr_str
    assert "***" in repr_str
    assert "nova-2" in repr_str


# --- Test D: Missing Key Produces Clear Error When Explicitly Requested ---

def test_missing_deepgram_key_error_when_explicitly_requested():
    """Verify clear ValueError is raised only when Deepgram mode is explicitly requested without a key."""
    with patch.object(settings, "DEEPGRAM_API_KEY", None):
        # Explicit request for deepgram should fail with descriptive guidance
        with pytest.raises(ValueError) as exc_info:
            get_stt_provider("deepgram")
        assert "DEEPGRAM_API_KEY is not set" in str(exc_info.value)

        # Explicit request for mock should always succeed
        mock_provider = get_stt_provider("mock")
        assert isinstance(mock_provider, MockSTTProvider)


# --- Test E: Deepgram Response Parsing with Representative Payload ---

def test_deepgram_response_parsing_representative_payload():
    """Verify parse_deepgram_response accurately extracts fields from Deepgram streaming JSON."""
    raw_payload = {
        "type": "Results",
        "channel_index": [0, 1],
        "duration": 1.45,
        "start": 4.5,
        "is_final": True,
        "speech_final": True,
        "channel": {
            "alternatives": [
                {
                    "transcript": "This is Officer Miller from the Federal Police Department.",
                    "confidence": 0.985,
                    "words": [
                        {"word": "this", "start": 4.5, "end": 4.7, "confidence": 0.99},
                        {"word": "is", "start": 4.7, "end": 4.9, "confidence": 0.98},
                    ],
                }
            ]
        },
    }

    segment = DeepgramSTTProvider.parse_deepgram_response(
        response_json=raw_payload,
        session_id="session-parse-test",
        speaker=SpeakerType.CALLER,
    )

    assert segment is not None
    assert segment.session_id == "session-parse-test"
    assert segment.speaker == SpeakerType.CALLER
    assert segment.text == "This is Officer Miller from the Federal Police Department."
    assert segment.timestamp == 4.5
    assert segment.is_final is True


# --- Test F: Partial and Final Transcript Handling ---

def test_partial_and_final_transcript_handling():
    """Verify distinction between interim (is_final=False) and final (is_final=True) transcripts."""
    # Interim / partial utterance
    interim_payload = {
        "is_final": False,
        "start": 1.0,
        "channel": {
            "alternatives": [{"transcript": "This is Officer Miller", "confidence": 0.85}]
        },
    }
    interim_seg = DeepgramSTTProvider.parse_deepgram_response(
        interim_payload, session_id="s1"
    )
    assert interim_seg is not None
    assert interim_seg.text == "This is Officer Miller"
    assert interim_seg.is_final is False

    # Final utterance
    final_payload = {
        "is_final": True,
        "start": 1.0,
        "channel": {
            "alternatives": [
                {
                    "transcript": "This is Officer Miller from the Federal Police Department.",
                    "confidence": 0.98,
                }
            ]
        },
    }
    final_seg = DeepgramSTTProvider.parse_deepgram_response(
        final_payload, session_id="s1"
    )
    assert final_seg is not None
    assert final_seg.text == "This is Officer Miller from the Federal Police Department."
    assert final_seg.is_final is True

    # Empty payload (no alternatives / empty text)
    empty_payload = {
        "is_final": True,
        "channel": {"alternatives": [{"transcript": "   "}]},
    }
    empty_seg = DeepgramSTTProvider.parse_deepgram_response(
        empty_payload, session_id="s1"
    )
    assert empty_seg is None


# --- Test G: Existing StreamingPipeline Remains Compatible ---

@pytest.mark.asyncio
async def test_streaming_pipeline_compatibility():
    """Verify existing StreamingPipeline functions with mock and custom STT providers."""
    chunks = ["You must pay five hundred dollars in gift cards immediately."]
    results = await streaming_pipeline.run_simulation(
        session_id="session-pipeline-compat",
        chunks=chunks,
        broadcast=False,
    )

    assert len(results) == 1
    assert results[0]["segment"].text == chunks[0]
    assert len(results[0]["matches"]) > 0
    assert results[0]["risk"].overall_score > 0.0


# --- Test I: Deepgram Streaming with Mocked WebSocket ---

@pytest.mark.asyncio
async def test_deepgram_streaming_with_mocked_websocket():
    """Verify DeepgramSTTProvider connects, sends audio, and yields parsed segments using a mocked WebSocket."""
    provider = DeepgramSTTProvider(api_key="mock-valid-key")

    mock_ws = AsyncMock()
    # Mock incoming messages from Deepgram
    mock_messages = [
        json.dumps({
            "is_final": True,
            "start": 0.5,
            "channel": {
                "alternatives": [
                    {"transcript": "This is a live test from Deepgram.", "confidence": 0.96}
                ]
            },
        })
    ]

    async def mock_iter():
        for m in mock_messages:
            yield m

    mock_ws.__aiter__.side_effect = mock_iter

    # Mock websockets.connect context manager
    mock_connect = AsyncMock()
    mock_connect.__aenter__.return_value = mock_ws
    mock_connect.__aexit__.return_value = None

    audio_chunks = [b"\x00\x01\x02\x03", b"\x04\x05\x06\x07"]

    with patch("websockets.connect", return_value=mock_connect):
        emitted_segments = []
        async for segment in provider.stream_transcripts(
            session_id="session-mocked-ws",
            input_data=audio_chunks,
        ):
            emitted_segments.append(segment)

        assert len(emitted_segments) == 1
        assert emitted_segments[0].text == "This is a live test from Deepgram."
        assert emitted_segments[0].is_final is True
        assert emitted_segments[0].timestamp == 0.5
