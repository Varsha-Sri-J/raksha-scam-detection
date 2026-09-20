import time
from typing import List, Optional
from backend.app.config import settings
from backend.app.models import (
    CallSession,
    RiskAssessment,
    RiskTier,
    TacticMatch,
    TranscriptSegment,
)


class RiskEngine:
    """Core Risk Engine foundation.

    In Phase 1, this engine provides a baseline, un-hallucinated risk assessment
    (score: 0.0, tier: SAFE, no triggered tactics).
    In Phase 2, this will integrate with the Semantic Classifier and Sentence
    Transformers in the `ai/` package to evaluate live manipulation tactics.
    """

    def __init__(self, baseline_score: float = settings.BASELINE_RISK_SCORE) -> None:
        self.baseline_score = baseline_score

    def evaluate_segment(self, segment: TranscriptSegment) -> List[TacticMatch]:
        """Evaluate a single transcript segment for manipulation tactics.

        Phase 1: Returns an empty list (no fake detections).
        Phase 2: Will invoke the semantic tactic classifier.
        """
        # Phase 1 foundation: baseline without synthetic hallucination
        return []

    def evaluate_session(self, session: CallSession) -> RiskAssessment:
        """Evaluate the overall risk of an active call session.

        Phase 1: Returns a baseline SAFE assessment with 0.0 risk score.
        Phase 2: Will aggregate tactic matches, temporal co-occurrence, and escalation velocity.
        """
        return RiskAssessment(
            session_id=session.session_id,
            overall_score=self.baseline_score,
            risk_tier=RiskTier.SAFE,
            triggered_tactics=[],
            timestamp=time.time(),
        )


# Global singleton instance
risk_engine = RiskEngine()
