import pytest
from backend.app.models import (
    CallSession,
    ManipulationCategory,
    RiskAssessment,
    RiskTier,
    TacticMatch,
    TranscriptSegment,
)
from backend.app.risk_engine import RiskEngine, risk_engine
from ai.classifier import semantic_classifier


@pytest.fixture(scope="module", autouse=True)
def init_classifier():
    """Ensure classifier is initialized for any end-to-end integration tests."""
    semantic_classifier.initialize()


# --- Scenario A: Neutral Conversation -> SAFE (0.0) ---

def test_scenario_a_neutral_conversation():
    """Neutral conversation with no tactics produces 0.0 risk score and SAFE tier."""
    engine = RiskEngine()
    assessment = engine.calculate_risk(
        session_id="session-neutral",
        new_matches=[],
        previous_assessment=None,
    )
    assert assessment.overall_score == 0.0
    assert assessment.risk_tier == RiskTier.SAFE
    assert len(assessment.accumulated_tactics) == 0
    assert assessment.score_delta == 0.0
    assert "safe" in assessment.explanation.lower()


# --- Scenario B: Legitimate Urgent Hospital Conversation -> Below High Risk ---

def test_scenario_b_legitimate_urgent_hospital_call():
    """Legitimate urgent medical call has urgency, but remains below high-risk threshold."""
    # End-to-end test using actual text through evaluate_segment
    segment = TranscriptSegment(
        session_id="session-hospital",
        text=(
            "Hello Mr. Davis, this is Dr. Emily from St. Jude Hospital. "
            "Your daughter had an acute asthma attack and is in the emergency room. "
            "Please come to the hospital immediately."
        ),
    )
    matches, assessment = risk_engine.evaluate_segment(segment)

    # Must remain strictly below HIGH risk (score < 75.0)
    assert assessment.overall_score < 50.0
    assert assessment.risk_tier in [RiskTier.SAFE, RiskTier.LOW]
    assert ManipulationCategory.FINANCIAL_REDIRECTION not in assessment.accumulated_tactics
    assert ManipulationCategory.INFORMATION_PHISHING not in assessment.accumulated_tactics


# --- Scenario C: Single Urgency Statement -> Never Critical ---

def test_scenario_c_single_urgency_statement():
    """A single isolated urgency statement must not trigger high or critical risk."""
    engine = RiskEngine()
    match = TacticMatch(
        tactic=ManipulationCategory.URGENCY,
        confidence=0.95,
        evidence_text="You must act within the next 15 minutes!",
    )
    assessment = engine.calculate_risk(
        session_id="session-urgency-only",
        new_matches=[match],
        previous_assessment=None,
    )
    # Urgency cap is 22.0, well within SAFE/LOW
    assert assessment.overall_score <= 25.0
    assert assessment.risk_tier in [RiskTier.SAFE, RiskTier.LOW]
    assert "safeguard" in assessment.explanation.lower() or "isolated urgency" in assessment.explanation.lower()


# --- Scenario D: Authority Impersonation Only -> Elevated but Controlled Risk ---

def test_scenario_d_authority_only():
    """Authority claim alone produces elevated, but controlled risk (e.g. LOW tier)."""
    engine = RiskEngine()
    match = TacticMatch(
        tactic=ManipulationCategory.AUTHORITY_IMPERSONATION,
        confidence=0.95,
        evidence_text="This is Officer Miller from the Federal Police Department.",
    )
    assessment = engine.calculate_risk(
        session_id="session-auth-only",
        new_matches=[match],
        previous_assessment=None,
    )
    assert 15.0 <= assessment.overall_score <= 35.0
    assert assessment.risk_tier in [RiskTier.SAFE, RiskTier.LOW]


# --- Scenario E: Authority + Fear + Urgency -> Substantially Elevated Risk ---

def test_scenario_e_authority_fear_urgency():
    """Co-occurrence of Authority, Fear, and Urgency escalates to HIGH risk."""
    engine = RiskEngine()
    matches = [
        TacticMatch(
            tactic=ManipulationCategory.AUTHORITY_IMPERSONATION,
            confidence=0.95,
            evidence_text="This is Officer Miller from the Federal Police Department.",
        ),
        TacticMatch(
            tactic=ManipulationCategory.FEAR_INTIMIDATION,
            confidence=0.90,
            evidence_text="An arrest warrant has been issued in your name for criminal fraud.",
        ),
        TacticMatch(
            tactic=ManipulationCategory.URGENCY,
            confidence=0.85,
            evidence_text="You must resolve this within 15 minutes before officers arrive.",
        ),
    ]
    assessment = engine.calculate_risk(
        session_id="session-triad",
        new_matches=matches,
        previous_assessment=None,
    )
    # Should be at least HIGH risk tier (>= 75.0)
    assert assessment.overall_score >= 70.0
    assert assessment.risk_tier in [RiskTier.HIGH, RiskTier.CRITICAL]
    assert "co-occurrence" in assessment.explanation.lower() or "synergy" in assessment.explanation.lower()


# --- Scenario F: Full Scam Nexus -> HIGH / CRITICAL Risk ---

def test_scenario_f_full_scam_nexus():
    """Authority + Fear + Urgency + Isolation + Credential/Financial request produces CRITICAL risk."""
    engine = RiskEngine()
    matches = [
        TacticMatch(
            tactic=ManipulationCategory.AUTHORITY_IMPERSONATION,
            confidence=0.95,
            evidence_text="This is Officer Miller from the Federal Police Department.",
        ),
        TacticMatch(
            tactic=ManipulationCategory.FEAR_INTIMIDATION,
            confidence=0.90,
            evidence_text="You will be arrested and put in prison if you fail to cooperate.",
        ),
        TacticMatch(
            tactic=ManipulationCategory.URGENCY,
            confidence=0.85,
            evidence_text="Every second counts, act immediately.",
        ),
        TacticMatch(
            tactic=ManipulationCategory.ISOLATION_SECRECY,
            confidence=0.85,
            evidence_text="Do not hang up this call and do not tell your family.",
        ),
        TacticMatch(
            tactic=ManipulationCategory.INFORMATION_PHISHING,
            confidence=0.90,
            evidence_text="Read me the six digit verification code sent to your phone right now.",
        ),
    ]
    assessment = engine.calculate_risk(
        session_id="session-nexus",
        new_matches=matches,
        previous_assessment=None,
    )
    assert assessment.overall_score >= 90.0
    assert assessment.risk_tier == RiskTier.CRITICAL
    assert len(assessment.accumulated_tactics) == 5
    assert assessment.overall_score <= 100.0


# --- Scenario G: Repeated Credential Requests -> Repetition Growth & Deduplication ---

def test_scenario_g_repeated_credential_requests():
    """Repeated distinct credential requests increase score; identical evidence does not add infinite score."""
    engine = RiskEngine()

    # Request 1
    match1 = TacticMatch(
        tactic=ManipulationCategory.INFORMATION_PHISHING,
        confidence=0.85,
        evidence_text="Tell me your bank account password.",
    )
    state1 = engine.calculate_risk("session-rep", [match1], None)

    # Request 2 (different wording)
    match2 = TacticMatch(
        tactic=ManipulationCategory.INFORMATION_PHISHING,
        confidence=0.85,
        evidence_text="Now tell me the OTP code that just arrived.",
    )
    state2 = engine.calculate_risk("session-rep", [match2], state1)

    # Score should increase with second distinct evidence
    assert state2.overall_score > state1.overall_score
    assert state2.score_delta > 0

    # Request 3 (Exact duplicate of Request 2)
    match3 = TacticMatch(
        tactic=ManipulationCategory.INFORMATION_PHISHING,
        confidence=0.85,
        evidence_text="Now tell me the OTP code that just arrived.",
    )
    state3 = engine.calculate_risk("session-rep", [match3], state2)

    # Duplicate evidence should NOT increase score
    assert state3.overall_score == state2.overall_score
    assert state3.score_delta == 0.0


# --- Score Bounds and Determinism ---

def test_risk_score_bounds_and_determinism():
    """Score must strictly respect [0, 100] bounds and be perfectly reproducible."""
    engine = RiskEngine()
    matches = [
        TacticMatch(tactic=cat, confidence=1.0, evidence_text=f"Extreme evidence for {cat.value}")
        for cat in ManipulationCategory
    ]

    assessment1 = engine.calculate_risk("session-bounds", matches, None)
    assessment2 = engine.calculate_risk("session-bounds", matches, None)

    assert 0.0 <= assessment1.overall_score <= 100.0
    # Determinism: exact same score and explanation
    assert assessment1.overall_score == assessment2.overall_score
    assert assessment1.explanation == assessment2.explanation
    assert assessment1.risk_tier == RiskTier.CRITICAL
