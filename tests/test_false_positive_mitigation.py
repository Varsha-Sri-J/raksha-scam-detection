# Tests for False-Positive Mitigation on Legitimate Urgent Calls.

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
