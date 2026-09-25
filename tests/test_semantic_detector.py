import pytest
from ai.classifier import SemanticClassifier, semantic_classifier
from ai.embeddings import embedding_engine
from backend.app.models import ManipulationCategory, TranscriptSegment


@pytest.fixture(scope="module", autouse=True)
def initialize_classifier():
    """Ensure the semantic classifier is initialized once for all tests."""
    semantic_classifier.initialize()


# --- Test A: Known Scam Wording ---

def test_known_scam_wording():
    """Known scam phrase: police impersonation and threat of arrest."""
    text = (
        "This is Officer Miller from the Federal Police Department. "
        "An arrest warrant has been issued in your name for criminal money laundering."
    )
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    assert ManipulationCategory.AUTHORITY_IMPERSONATION in detected_tactics
    assert ManipulationCategory.FEAR_INTIMIDATION in detected_tactics

    # Verify structured fields
    for match in matches:
        assert match.confidence >= 0.48
        assert len(match.evidence_text) > 0
        assert match.explanation is not None
        assert match.description is not None


# --- Test B: Rewritten / Novel Scam Wording ---

@pytest.mark.parametrize(
    "phrase,expected_tactic",
    [
        # Information Phishing variations
        ("Give me your OTP.", ManipulationCategory.INFORMATION_PHISHING),
        ("Read the six digit security code you just received.", ManipulationCategory.INFORMATION_PHISHING),
        ("Tell me the verification number that came to your phone.", ManipulationCategory.INFORMATION_PHISHING),
        # Financial Redirection variations
        ("Go to the store and get five hundred dollars in Apple gift cards.", ManipulationCategory.FINANCIAL_REDIRECTION),
        ("Please install AnyDesk on your computer so I can access your screen.", ManipulationCategory.FINANCIAL_REDIRECTION),
        # Isolation variations
        ("Keep this between us, do not let your daughter or spouse know what we are discussing.", ManipulationCategory.ISOLATION_SECRECY),
        ("Stay on the line with me, do not hang up under any circumstances.", ManipulationCategory.ISOLATION_SECRECY),
        # False Salvation variations
        ("I am the only one who can help clear your name from this investigation.", ManipulationCategory.RELIEF_FALSE_SALVATION),
    ],
)
def test_rewritten_novel_scam_wording(phrase, expected_tactic):
    """Novel and rewritten scam wording should map to the appropriate manipulation category."""
    matches = semantic_classifier.classify_text(phrase)
    detected_tactics = {m.tactic for m in matches}

    assert expected_tactic in detected_tactics, (
        f"Expected tactic '{expected_tactic}' for phrase '{phrase}', "
        f"but detected: {[m.tactic for m in matches]}"
    )


# --- Test B2: Multilingual & Code-Mixed (Hinglish) Scam Wording ---

@pytest.mark.parametrize(
    "phrase,expected_tactic",
    [
        ("Aapka bank account freeze ho gaya hai, turant OTP bataiye.", ManipulationCategory.INFORMATION_PHISHING),
        ("Main Mumbai Police Crime Branch se Officer Sharma bol raha hu.", ManipulationCategory.AUTHORITY_IMPERSONATION),
        ("Aapka sara balance RBI safety account mein UPI se transfer karo.", ManipulationCategory.FINANCIAL_REDIRECTION),
        ("Call disconnect mat karna warna police aapke ghar aayegi.", ManipulationCategory.ISOLATION_SECRECY),
        ("Aapke naam par arrest warrant issue ho gaya hai aur police bhej rahe hain.", ManipulationCategory.FEAR_INTIMIDATION),
    ],
)
def test_multilingual_hinglish_code_mixed_scam_wording(phrase, expected_tactic):
    """Multilingual and Hinglish code-mixed scam wording should map to appropriate manipulation categories."""
    matches = semantic_classifier.classify_text(phrase)
    detected_tactics = {m.tactic for m in matches}

    assert expected_tactic in detected_tactics, (
        f"Expected tactic '{expected_tactic}' for Hinglish phrase '{phrase}', "
        f"but detected: {[m.tactic for m in matches]}"
    )


# --- Test C: Multi-Tactic Scam Conversation ---

def test_multi_tactic_scam():
    """A single aggressive scam statement exhibiting multiple simultaneous coercion tactics."""
    text = (
        "This is Special Agent Vance from the Cybercrime Investigation Bureau. "
        "You have only 15 minutes to transfer your funds to our secure safety account, "
        "and you cannot tell your family or disconnect this line."
    )
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    # Should detect at least 3 distinct tactics
    assert ManipulationCategory.AUTHORITY_IMPERSONATION in detected_tactics
    assert ManipulationCategory.FINANCIAL_REDIRECTION in detected_tactics
    assert ManipulationCategory.ISOLATION_SECRECY in detected_tactics
    # Urgency might also be triggered
    assert len(detected_tactics) >= 3


# --- Test D: Legitimate Urgent Hospital Conversation ---

def test_legitimate_urgent_hospital_call():
    """Legitimate urgent medical call: urgency exists, but NO scam tactics."""
    text = (
        "Hello Mr. Davis, this is Dr. Emily from St. Jude Hospital. "
        "Your daughter had an acute asthma attack and is in the emergency room. "
        "Please come to the hospital immediately."
    )
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    # Scam extortion tactics MUST NOT be triggered
    assert ManipulationCategory.FINANCIAL_REDIRECTION not in detected_tactics
    assert ManipulationCategory.INFORMATION_PHISHING not in detected_tactics
    assert ManipulationCategory.ISOLATION_SECRECY not in detected_tactics
    assert ManipulationCategory.FEAR_INTIMIDATION not in detected_tactics
    assert ManipulationCategory.CONFUSION_OVERWHELM not in detected_tactics


# --- Test E: Legitimate Bank Verification Call ---

def test_legitimate_bank_verification_call():
    """Legitimate bank verification asking simple yes/no without credential harvesting or extortion."""
    text = (
        "Good morning, this is the automated fraud alert service from Chase Bank. "
        "We detected an unusual charge of $42.50 at Target on your card ending in 1234. "
        "Did you authorize this charge? Please reply yes or no."
    )
    matches = semantic_classifier.classify_text(text)
    detected_tactics = {m.tactic for m in matches}

    # Should NOT trigger credential phishing or financial redirection
    assert ManipulationCategory.INFORMATION_PHISHING not in detected_tactics
    assert ManipulationCategory.FINANCIAL_REDIRECTION not in detected_tactics
    assert ManipulationCategory.ISOLATION_SECRECY not in detected_tactics
    assert ManipulationCategory.FEAR_INTIMIDATION not in detected_tactics


# --- Test F: Neutral Conversation ---

@pytest.mark.parametrize(
    "neutral_text",
    [
        "Hey grandma, just calling to see how you are doing today. Did you get a chance to water the tomatoes?",
        "The recipe calls for two cups of flour, one teaspoon of vanilla, and three eggs.",
        "The weather in Seattle today is partly cloudy with a high around 65 degrees.",
    ],
)
def test_neutral_conversation(neutral_text):
    """Completely neutral conversation should not trigger any manipulation tactics."""
    matches = semantic_classifier.classify_text(neutral_text)
    assert len(matches) == 0, f"Expected 0 matches for '{neutral_text}', but got: {matches}"


# --- Test G: TranscriptSegment Interface & Performance ---

def test_classify_segment_interface():
    """Verify classify_segment correctly unwraps a TranscriptSegment object."""
    segment = TranscriptSegment(
        session_id="session-test-01",
        text="Download AnyDesk immediately so we can inspect your machine.",
    )
    matches = semantic_classifier.classify_segment(segment)
    detected_tactics = {m.tactic for m in matches}

    assert ManipulationCategory.FINANCIAL_REDIRECTION in detected_tactics


def test_model_loaded_once():
    """Verify embedding model is loaded once and cached."""
    assert embedding_engine.is_loaded is True
    # Subsequent calls to load_model should be no-ops
    embedding_engine.load_model()
    assert embedding_engine.is_loaded is True
