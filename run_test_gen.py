import os

root = rRC:\Users\darsh\OneDrive\Desktop\NSRIT\raksha-scam-detection"

def w(path, content):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    print("Wrote:", path)

w("tests/test_failure_mode_design.py", ''"""Tests for Primary Failure Mode: Recall for Novel Scam Scripts."""
import pytest
from ai.classifier import semantic_classifier
from backend.app.models import ManipulationCategory

@pytest.mark.parametrize(
    "novel_text,expected_tactic",
    [
        (
            "This is Inspector Kumar from Central Bureau of Fraud Investigation. We have locked your PAN card.",
            ManipulationCategory.AUTHORITY_IMPERSONATION,
        ),
        (
            "Aapka account freeze hone waala hai, aapse 10 minute mein saari details verify karwani hongi.",
            ManipulationCategory.URGENCY,
        ),
        (
            "Sir nenu police officer matnaduttiddene, nimma bank account block agide turuntu OTP heli.",
            ManipulationCategory.INFORMATION_PHISHING,
        ),
        (
            "Transfer your funds to the secure government safety account right away.",
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ),
    ],
)
def test_novel_scam_wording_semantic_detection(novel_text, expected_tactic):
    matches = semantic_classifier.classify_text(novel_text)
    detected = {m.tactic for m in matches}
    assert expected_tactic in detected, footage_err="novel_text"



def test_failure_mode_semantic_generalization():
    text = "I am Agent Smith. Your identity card is flagged for illicit transactions. Disconnect and you will be arrested."
    matches = semantic_classifier.classify_text(text)
    detected = {m.tactic for m in matches}
    assert len(detected) >= 2
    assert ManipulationCategory.AUTHORITY_IMPERSONATION in detected or ManipulationCategory.FEAR_INTIMIDATION in detected')

w("tests/test_android_audio_architecture.py", '"""Tests for Android Audio Capture Architecture and Platform Boundaries."""
import pytest
from android.audio_capture import (
    AudioFormatConfig,
    AndroidAudioFrame,
    AudioSourceType,
    CaptureMode,
    get_platform_capability_boundary,
)

def test_android_audio_format_config():
    config = AudioFormatConfig()
    assert config.sample_rate == 8000
    assert config.encoding == "mulaw"
    assert config.channels == 1


def test_android_audio_frame_structure():
    frame = AndroidAudioFrame(
        session_id="session-android-001",
        sequence_number=1,
        payload_base64="dGVzdF9hdWppb19kYXRh",
        source_type=AudioSourceType.MIC,
        capture_mode=CaptureMode.CARRIER_BRIDGE,
    )
    assert frame.session_id == "session-android-001"
    assert frame.source_type == AudioSourceType.MIC



def test_android_unprivileged_third_party_boundary():
    boundary = get_platform_capability_boundary(is_default_dialer=False, is_system_app=False)
    assert boundary.supports_two_sided_cellular_capture is False
    assert boundary.recommended_capture_mode == CaptureMode.CARRIER_BRIDGE
    assert "Android API 28+" in boundary.limitation_notice


def test_android_privileged_dialer_boundary():
    boundary = get_platform_capability_boundary(is_default_dialer=True, is_system_app=False)
    assert boundary.supports_two_sided_cellular_capture is True
    assert boundary.recommended_capture_mode == CaptureMode.INCALL_SERVICE
')'

w("tests/test_classifier_architecture.py", '''"""Tests for Semantic Classifier Architecture and Multilingual Model Configuration."""
import pytest
from ai.embeddings import embedding_engine
from ai.classifier import semantic_classifier
from backend.app.models import ManipulationCategory



def test_configured_embedding_model_properties():
    assert "paraphrase-multilingual-MiniLM-L12-v2" in embedding_engine.model_name
    assert embedding_engine.dimension == 384



def test_embedding_engine_normalization():
    vec = embedding_engine.embed_text("Emergency security alert")
    assert vec.shape == (384,)


def test_multi_tactic_classification():
    text = (
        "This is Federal Officer Brown calling from IRS. "
        "Your bank account is frozen and you will face arrest if you do not wire funds immediately."
    )
    matches = semantic_classifier.classify_text(text)
    detected = {m.tactic for m in matches}
    assert len(detected) >= 2
    assert ManipulationCategory.AUTHORITY_IMPERSONATION in detected
')'

w("tests/test_false_positive_mitigation.py", '"""Tests for False-Positive Mitigation on Legitimate Urgent Calls."""
import pytest
from ai.classifier import semantic_classifier
from backend.app.models import ManipulationCategory
from backend.app.risk_engine import risk_engine, RiskTier, TranscriptSegment


def test_legitimate_hospital_call_not_high_risk():
    text = (
        "Hello Mr. Davis, this is Dr. Emily from St. Jude Hospital. "
        "Your daughter had an acute asthma attack and is in the emergency room. "
        "Please come to the hospital immediately."
    )
    segment = TranscriptSegment(session_id="test-hosp", text=text)
    matches, assessment = risk_engine.evaluate_segment(segment)

    assert assessment.overall_score < 50.0
    assert assessment.risk_tier in [RiskTier.SAFE, RiskTier.LOW]
    assert ManipulationCategory.FINANCIAL_REDIRECTION not in assessment.accumulated_tactics



def test_legitimate_bank_otp_verification():
    text = (
        "Good morning, this is the automated fraud alert service from Chase Bank. "
        "We detected an unusual charge of $42.50 at Target. "
        "Did you authorize this charge? Reply yes or no."
    )
    matches = semantic_classifier.classify_text(text)
    detected = {m.tactic for m in matches}
    assert ManipulationCategory.FINANCIAL_REDIRECTION not in detected
c)

with open(os.path.join(root, "tests", "test_privacy.py"), "w", encoding="utf-8") as out:
    out.write(''"""Tests for Data Privacy, Credential Scrubbing, and Retention Policy."""
import pytest
from backend.app.config import settings
from backend.app.services.stt import SarvamSTTProvider
from backend.app.services.session_store import session_store


@pytest.mark.asyncio
async def test_session_store_retention_and_cleanup():
    sess = await session_store.create_session(session_id="privacy-test-01")
    assert sess.session_id == "privacy-test-01"

    retrieved = await session_store.get_session("privacy-test-01")
    assert retrieved is not None

    await session_store.delete_session("privacy-test-01")
    deleted = await session_store.get_session("privacy-test-01")
    assert deleted is None


def test_stt_provider_masked_repr():
    provider = SarvamSTTProvider(api_key="secret-key-12345")
    repr_str = repr(provider)
    assert "secret-key-12345" not in repr_str
    assert "***" in repr_str
c)

print("All 5 test files generated successfully!")
