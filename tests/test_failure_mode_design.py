# Tests for Primary Failure Mode: Recall for Novel Scam Scripts.

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
            "Aapka account freeze hone waala hai, aapse 10 minute mein saark details verify karwani hongi.",
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
    assert expected_tactic in detected, f"Expected {expected_tactic} in semantic matches for: {novel_text}"



def test_failure_mode_semantic_generalization():
    text = "I am Agent Smith. Your identity card is flagged for illicit transactions. Disconnect and you will be arrested."
    matches = semantic_classifier.classify_text(text)
    detected = {m.tactic for m in matches}
    assert len(detected) >= 2
    assert ManipulationCategory.AUTHORITY_IMPERSONATION in detected or ManipulationCategory.FEAR_INTIMIDATION in detected
