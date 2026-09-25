import pytest

from ai.classifier import semantic_classifier
from backend.app.models import ManipulationCategory, RiskTier
from backend.app.risk_engine import risk_engine


@pytest.mark.parametrize(
    "text,required_tactics",
    [
        (
            "This is a fraud review team with the Treasury Department. We need to verify your identity before we freeze the account and you should keep this quiet while we sort it out.",
            {
                ManipulationCategory.AUTHORITY_IMPERSONATION,
                ManipulationCategory.URGENCY,
                ManipulationCategory.FEAR_INTIMIDATION,
                ManipulationCategory.INFORMATION_PHISHING,
            },
        ),
        (
            "We flagged a suspicious purchase on your account. Please read the 6-digit code that just arrived so we can secure the payment and confirm your identity.",
            {ManipulationCategory.INFORMATION_PHISHING},
        ),
    ],
)
def test_indirect_scam_language_still_triggers_manipulation_detection(text, required_tactics):
    """Indirect or conversational scams should still match the intended manipulation category."""
    matches = semantic_classifier.classify_text(text)
    detected = {match.tactic for match in matches}

    for tactic in required_tactics:
        assert tactic in detected, (
            f"Expected '{tactic}' in matches for '{text}', but got {[m.tactic for m in matches]}"
        )


def test_multi_tactic_pressure_campaign_escales_to_critical_risk():
    """A coercive call mixing authority, isolation, urgency, and money transfer should hit critical risk."""
    text = (
        "This is Special Agent Vance from the Cybercrime Investigation Bureau. "
        "You have only 15 minutes to transfer your funds to our secure safety account, "
        "and you cannot tell your family or disconnect this line."
    )
    matches = semantic_classifier.classify_text(text)
    detected = {match.tactic for match in matches}

    assert ManipulationCategory.AUTHORITY_IMPERSONATION in detected
    assert ManipulationCategory.ISOLATION_SECRECY in detected
    assert ManipulationCategory.FINANCIAL_REDIRECTION in detected
    assert ManipulationCategory.URGENCY in detected

    risk = risk_engine.calculate_risk(session_id="adversarial-critical", new_matches=matches)
    assert risk.risk_tier == RiskTier.CRITICAL
    assert risk.overall_score >= 90.0


def test_legitimate_emergency_call_does_not_trigger_scam_patterns():
    """Urgent medical contact should register as a safe call, not an extortion scam."""
    text = (
        "Hello, this is Dr. Emily from St. Jude Hospital. "
        "Your daughter had an acute asthma attack and is in the emergency room. "
        "Please come to the hospital immediately."
    )
    matches = semantic_classifier.classify_text(text)

    assert matches == []


def test_false_salvation_and_secrecy_mixed_message_is_flagged_but_not_critical():
    """A coercive but not fully financial scam can still be categorized as a low-risk manipulation pattern."""
    text = (
        "I am the only one who can keep you out of jail. "
        "Stay on the line and do not tell anyone what I am saying."
    )
    matches = semantic_classifier.classify_text(text)
    detected = {match.tactic for match in matches}

    assert ManipulationCategory.ISOLATION_SECRECY in detected
    assert ManipulationCategory.RELIEF_FALSE_SALVATION in detected
    assert ManipulationCategory.FEAR_INTIMIDATION in detected

    risk = risk_engine.calculate_risk(session_id="adversarial-low", new_matches=matches)
    assert risk.risk_tier in {RiskTier.LOW, RiskTier.MEDIUM}
    assert risk.overall_score < 75.0
