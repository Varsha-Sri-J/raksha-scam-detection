import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai.classifier import SemanticClassifier
from ai.embeddings import EmbeddingEngine
from backend.app.config import settings
from backend.app.models import (
    ManipulationCategory,
    SpeakerType,
    TranscriptSegment,
)
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.stt import (
    BaseSTTProvider,
    DeepgramSTTProvider,
    MockSTTProvider,
    SarvamSTTProvider,
    get_stt_provider,
)


# =====================================================================
# A. TRANSCRIPT MODEL COMPATIBILITY
# =====================================================================

def test_transcript_model_backward_compatibility():
    """Verify old construction without language metadata still works cleanly."""
    seg = TranscriptSegment(
        session_id="session-legacy-01",
        text="Hello, this is a test call.",
    )
    assert seg.session_id == "session-legacy-01"
    assert seg.text == "Hello, this is a test call."
    assert seg.detected_language is None
    assert seg.detected_languages == []

    dumped = seg.model_dump()
    assert dumped["session_id"] == "session-legacy-01"
    assert dumped["detected_language"] is None
    assert dumped["detected_languages"] == []


def test_transcript_model_multilingual_metadata():
    """Verify multilingual metadata fields can be stored and serialized."""
    seg = TranscriptSegment(
        session_id="session-multi-01",
        text="Aapka account block hone wala hai, share OTP.",
        detected_language="hi-IN",
        detected_languages=["hi", "en"],
    )
    assert seg.detected_language == "hi-IN"
    assert seg.detected_languages == ["hi", "en"]

    dumped = seg.model_dump()
    assert dumped["detected_language"] == "hi-IN"
    assert dumped["detected_languages"] == ["hi", "en"]


# =====================================================================
# B-I. SEMANTIC CLASSIFICATION TESTS (HINDI, CODE-MIXED, NOVEL, ETC.)
# =====================================================================

def test_hindi_semantic_detection():
    """B. Hindi scam text detection."""
    text = "Sir aapka bank account block hone wala hai, abhi OTP bataiye."
    from ai.classifier import semantic_classifier
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    assert ManipulationCategory.URGENCY in detected_tactics or ManipulationCategory.INFORMATION_PHISHING in detected_tactics
    assert len(matches) > 0


def test_hindi_english_code_mixed_detection():
    """C. Hindi-English code-mixed detection."""
    text = "Aapka account block hone wala hai. You need to share the OTP immediately."
    from ai.classifier import semantic_classifier
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    assert ManipulationCategory.URGENCY in detected_tactics
    assert ManipulationCategory.INFORMATION_PHISHING in detected_tactics


def test_kannada_english_code_mixed_detection():
    """D. Kannada-English code-mixed detection."""
    text = "Nimma bank account block agutte, please share your OTP."
    from ai.classifier import semantic_classifier
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    assert ManipulationCategory.URGENCY in detected_tactics or ManipulationCategory.INFORMATION_PHISHING in detected_tactics


def test_telugu_english_code_mixed_detection():
    """E. Telugu-English code-mixed detection."""
    text = "మీ account block అవుతుంది, please give me the OTP."
    from ai.classifier import semantic_classifier
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    assert ManipulationCategory.URGENCY in detected_tactics or ManipulationCategory.INFORMATION_PHISHING in detected_tactics


def test_multiple_tactics_multilingual_utterance():
    """F. Multiple tactics in one multilingual utterance."""
    text = "Sir nenu bank officer. Your account is under investigation, ippude OTP share maadi and don't tell your family."
    from ai.classifier import semantic_classifier
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    assert len(detected_tactics) >= 2


def test_legitimate_multilingual_urgent_call():
    """G. Legitimate urgent scenario should NOT trigger scam extortion tactics."""
    text = "Amma hospital ge bandiddare, please come immediately. Doctor has already started treatment."
    from ai.classifier import semantic_classifier
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    assert ManipulationCategory.INFORMATION_PHISHING not in detected_tactics
    assert ManipulationCategory.FINANCIAL_REDIRECTION not in detected_tactics
    assert ManipulationCategory.ISOLATION_SECRECY not in detected_tactics
    assert ManipulationCategory.FEAR_INTIMIDATION not in detected_tactics


@pytest.mark.parametrize(
    "neutral_text",
    [
        "Namma maneyalliellaru kshema. How was your weekend?",
        "The weather is nice today and I am drinking coffee.",
        "I am watching a movie on the television right now.",
    ],
)
def test_neutral_multilingual_conversation(neutral_text):
    """H. Neutral multilingual conversation should return no tactics."""
    from ai.classifier import semantic_classifier
    matches = semantic_classifier.classify_text(neutral_text)
    assert len(matches) == 0


def test_novel_multilingual_wording():
    """I. Novel wording that does not copy anchors verbatim."""
    text = "Mee bank account block avvakunda eroju verification code naku immediate ga send cheyandi."
    from ai.classifier import semantic_classifier
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    assert len(detected_tactics) > 0


# =====================================================================
# J. DEEPGRAM MULTILINGUAL CONFIG & METADATA TESTS
# =====================================================================

def test_deepgram_multilingual_url_config():
    """J. Deepgram configured with multilingual language value."""
    provider = DeepgramSTTProvider(api_key="mock_key", language="multi")
    url = provider.build_websocket_url()
    assert "language=multi" in url


def test_deepgram_response_parsing_with_language_metadata():
    """Deepgram response parser extracts detected language metadata."""
    sample_response = {
        "is_final": True,
        "start": 1.25,
        "detected_language": "hi-IN",
        "channel": {
            "alternatives": [
                {
                    "transcript": "Aapka account block hone wala hai.",
                    "confidence": 0.98,
                    "languages": ["hi", "en"],
                }
            ]
        },
    }
    seg = DeepgramSTTProvider.parse_deepgram_response(
        sample_response, session_id="deepgram-sess-01"
    )
    assert seg is not None
    assert seg.text == "Aapka account block hone wala hai."
    assert seg.detected_language == "hi-IN"
    assert seg.detected_languages == ["hi", "en"]


# =====================================================================
# K. STT PROVIDER FACTORY TESTS
# =====================================================================

def test_stt_provider_factory_mock():
    """Provider factory returns MockSTTProvider for mode='mock'."""
    provider = get_stt_provider("mock")
    assert isinstance(provider, MockSTTProvider)


def test_stt_provider_factory_deepgram():
    """Provider factory returns DeepgramSTTProvider when key configured."""
    with patch.object(settings, "DEEPGRAM_API_KEY", "test-deepgram-key"):
        provider = get_stt_provider("deepgram")
        assert isinstance(provider, DeepgramSTTProvider)


def test_stt_provider_factory_sarvam():
    """Provider factory returns SarvamSTTProvider when key configured."""
    with patch.object(settings, "SARVAM_API_KEY", "test-sarvam-key"):
        provider = get_stt_provider("sarvam")
        assert isinstance(provider, SarvamSTTProvider)


def test_stt_provider_factory_missing_sarvam_key():
    """Provider factory raises ValueError when SARVAM_API_KEY is missing."""
    with patch.object(settings, "SARVAM_API_KEY", None):
        with pytest.raises(ValueError, match="SARVAM_API_KEY is not set"):
            get_stt_provider("sarvam")


def test_stt_provider_factory_invalid():
    """Provider factory raises ValueError for invalid provider mode."""
    with pytest.raises(ValueError, match="Unsupported STT provider"):
        get_stt_provider("invalid_provider")


# =====================================================================
# L. SARVAM RESPONSE PARSER TESTS
# =====================================================================

def test_sarvam_response_parsing():
    """L. Parse Sarvam response JSON into TranscriptSegment."""
    sample_response = {
        "transcript": "Aapka account block hone wala hai, OTP bataiye.",
        "is_final": True,
        "language_code": "hi-IN",
        "detected_languages": ["hi", "en"],
        "timestamp": 1710000000.0,
    }
    seg = SarvamSTTProvider.parse_sarvam_response(
        sample_response, session_id="sarvam-sess-01"
    )
    assert seg is not None
    assert seg.text == "Aapka account block hone wala hai, OTP bataiye."
    assert seg.detected_language == "hi-IN"
    assert seg.detected_languages == ["hi", "en"]
    assert seg.is_final is True


def test_sarvam_response_parsing_empty():
    """Sarvam response parser returns None for empty text."""
    sample_response = {"transcript": "", "is_final": True}
    seg = SarvamSTTProvider.parse_sarvam_response(sample_response, session_id="s1")
    assert seg is None


# =====================================================================
# M. SARVAM STREAMING WITH MOCKED WEBSOCKET
# =====================================================================

@pytest.mark.asyncio
async def test_sarvam_streaming_mocked():
    """M. SarvamSTTProvider streams audio and yields TranscriptSegments with metadata."""
    provider = SarvamSTTProvider(api_key="mock_sarvam_key")
    audio_chunks = [b"fake_audio_chunk_1", b"fake_audio_chunk_2"]

    mock_response = json.dumps({
        "transcript": "Nimma account block agutte, share OTP.",
        "is_final": True,
        "language_code": "kn-IN",
        "detected_languages": ["kn", "en"],
    })

    class MockWebSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def send(self, data):
            pass

        async def __aiter__(self):
            yield mock_response

    with patch("websockets.connect", return_value=MockWebSocket()):
        segments = []
        async for seg in provider.stream_transcripts(
            session_id="sarvam-test-stream",
            input_data=audio_chunks,
        ):
            segments.append(seg)

        assert len(segments) == 1
        assert segments[0].text == "Nimma account block agutte, share OTP."
        assert segments[0].detected_language == "kn-IN"
        assert segments[0].detected_languages == ["kn", "en"]


# =====================================================================
# N. PIPELINE MULTILINGUAL COMPATIBILITY
# =====================================================================

@pytest.mark.asyncio
async def test_pipeline_multilingual_compatibility():
    """N. Process a multilingual segment through StreamingPipeline."""
    segment = TranscriptSegment(
        session_id="pipeline-multi-01",
        text="Aapka account block hone wala hai. Please tell me the OTP immediately.",
        detected_language="hi-IN",
        detected_languages=["hi", "en"],
    )

    result = await streaming_pipeline.process_segment(segment, broadcast=False)

    assert result["segment"].text == "Aapka account block hone wala hai. Please tell me the OTP immediately."
    assert result["segment"].detected_language == "hi-IN"
    assert result["segment"].detected_languages == ["hi", "en"]
    assert result["risk"] is not None
    assert result["risk"].overall_score >= 0.0
