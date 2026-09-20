import pytest
from pydantic import ValidationError
from backend.app.models import (
    CallSession,
    ManipulationCategory,
    RiskAssessment,
    RiskTier,
    SessionStatus,
    SpeakerType,
    TacticMatch,
    TranscriptSegment,
    WSMessage,
    WSMessageType,
)


def test_transcript_segment_defaults():
    segment = TranscriptSegment(
        session_id="test-session-123",
        text="Hello, this is officer John.",
        speaker=SpeakerType.CALLER,
    )
    assert segment.session_id == "test-session-123"
    assert segment.text == "Hello, this is officer John."
    assert segment.speaker == SpeakerType.CALLER
    assert segment.is_final is True
    assert segment.id is not None
    assert segment.timestamp > 0


def test_risk_assessment_baseline():
    assessment = RiskAssessment(session_id="session-abc")
    assert assessment.session_id == "session-abc"
    assert assessment.overall_score == 0.0
    assert assessment.risk_tier == RiskTier.SAFE
    assert len(assessment.triggered_tactics) == 0


def test_risk_assessment_score_bounds():
    # Valid score
    assessment = RiskAssessment(
        session_id="session-abc",
        overall_score=85.5,
        risk_tier=RiskTier.HIGH,
    )
    assert assessment.overall_score == 85.5

    # Invalid score > 100
    with pytest.raises(ValidationError):
        RiskAssessment(session_id="session-abc", overall_score=150.0)

    # Invalid score < 0
    with pytest.raises(ValidationError):
        RiskAssessment(session_id="session-abc", overall_score=-10.0)


def test_tactic_match_model():
    match = TacticMatch(
        tactic=ManipulationCategory.AUTHORITY_IMPERSONATION,
        confidence=0.92,
        evidence_text="This is the police department calling.",
    )
    assert match.tactic == ManipulationCategory.AUTHORITY_IMPERSONATION
    assert match.confidence == 0.92
    assert match.evidence_text == "This is the police department calling."


def test_call_session_defaults():
    session = CallSession()
    assert session.session_id is not None
    assert session.status == SessionStatus.ACTIVE
    assert session.caller_id == "Unknown"
    assert session.transcript_history == []
    assert session.latest_risk is None


def test_ws_message_model():
    msg = WSMessage(
        type=WSMessageType.TRANSCRIPT_STREAM,
        data={"text": "test stream"},
    )
    assert msg.type == WSMessageType.TRANSCRIPT_STREAM
    assert msg.data["text"] == "test stream"
    assert msg.timestamp > 0
