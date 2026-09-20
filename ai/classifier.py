from typing import List, Optional
from backend.app.models import ManipulationCategory, TacticMatch, TranscriptSegment
from ai.tactics import TACTIC_REGISTRY


class SemanticClassifier:
    """Semantic Manipulation Classifier stub for Phase 1.

    In Phase 2, this will calculate cosine similarity between transcript embeddings
    and the anchor phrases in `TACTIC_REGISTRY`, yielding calibrated tactic matches.
    """

    def __init__(self, similarity_threshold: float = 0.65) -> None:
        self.similarity_threshold = similarity_threshold

    def classify_segment(self, segment: TranscriptSegment) -> List[TacticMatch]:
        """Classify a single transcript segment against manipulation categories.

        Phase 1: Returns an empty list (zero synthetic hallucination).
        Phase 2: Computes semantic similarity against tactic embeddings.
        """
        return []

    def classify_text(self, text: str) -> List[TacticMatch]:
        """Classify raw text string against manipulation categories."""
        return []


# Global singleton instance
semantic_classifier = SemanticClassifier()
