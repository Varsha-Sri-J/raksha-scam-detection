import pytest
from backend.app.models import (
    RiskAssessment,
    RiskTier,
    SessionStatus,
    SpeakerType,
    TranscriptSegment,
)
from backend.app.services.session_store import session_store


@pytest.mark.asyncio
async def test_create_and_get_session():
    session = await session_store.create_session(
        caller_id="+1234567890",
        callee_id="+1987654321",
    )
    assert session is not None
    assert session.caller_id == "+1234567890"
    assert session.callee_id == "+1987654321"
    assert session.status == SessionStatus.ACTIVE

    retrieved = await session_store.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id


@pytest.mark.asyncio
async def test_add_transcript_segment():
    session = await session_store.create_session()
    segment = TranscriptSegment(
        session_id=session.session_id,
        speaker=SpeakerType.CALLER,
        text="Your card has been compromised.",
    )
    result = await session_store.add_transcript_segment(session.session_id, segment)
    assert result is not None
    assert result.text == "Your card has been compromised."

    updated_session = await session_store.get_session(session.session_id)
    assert len(updated_session.transcript_history) == 1
    assert updated_session.transcript_history[0].text == "Your card has been compromised."


@pytest.mark.asyncio
async def test_update_risk_assessment():
    session = await session_store.create_session()
    assessment = RiskAssessment(
        session_id=session.session_id,
        overall_score=0.0,
        risk_tier=RiskTier.SAFE,
    )
    result = await session_store.update_risk_assessment(session.session_id, assessment)
    assert result is not None
    assert result.overall_score == 0.0

    updated_session = await session_store.get_session(session.session_id)
    assert updated_session.latest_risk is not None
    assert updated_session.latest_risk.overall_score == 0.0


@pytest.mark.asyncio
async def test_end_session():
    session = await session_store.create_session()
    assert session.status == SessionStatus.ACTIVE

    ended = await session_store.end_session(session.session_id)
    assert ended is not None
    assert ended.status == SessionStatus.ENDED

    active_sessions = await session_store.list_sessions(status=SessionStatus.ACTIVE)
    assert session.session_id not in [s.session_id for s in active_sessions]
