import logging
import re
from typing import Any, Dict, List, Optional
import numpy as np

from backend.app.models import ManipulationCategory, TacticMatch, TranscriptSegment
from ai.embeddings import EmbeddingEngine, embedding_engine
from ai.tactics import TACTIC_REGISTRY, TacticDefinition

logger = logging.getLogger("raksha.ai.classifier")


class SemanticClassifier:
    """Semantic Manipulation Classifier for RAKSHA (Phase 2A).

    Evaluates input transcript segments against RAKSHA's 8 manipulation categories
    using cosine similarity between Sentence Transformer embeddings and curated
    tactic anchor representations.

    Features:
    - Precomputes and caches anchor embeddings once at load time.
    - Evaluates both full utterances and sentence-level segments for fine-grained evidence extraction.
    - Detects multiple co-occurring tactics in a single utterance.
    - Recognizes semantically rewritten or novel scam phrasing without keyword matching.
    - Generates zero fake or random scores; outputs genuine calibrated cosine similarities.
    - Generates NO risk score inside the classifier.
    """

    def __init__(
        self,
        engine: Optional[EmbeddingEngine] = None,
        similarity_threshold: float = 0.45,
    ) -> None:
        self.embedding_engine = engine or embedding_engine
        self.similarity_threshold = similarity_threshold
        self._anchor_cache: Dict[ManipulationCategory, Dict[str, Any]] = {}
        self._is_initialized = False

    def initialize(self) -> None:
        """Precompute and cache embeddings for all 8 manipulation categories."""
        if self._is_initialized:
            return

        logger.info("Initializing SemanticClassifier anchor embeddings...")
        self.embedding_engine.load_model()

        for category, tactic_def in TACTIC_REGISTRY.items():
            # Include anchor phrases and the formal tactic description
            anchor_texts = list(tactic_def.anchor_phrases) + [tactic_def.description]
            anchor_embeddings = self.embedding_engine.embed_batch(anchor_texts)

            self._anchor_cache[category] = {
                "definition": tactic_def,
                "texts": anchor_texts,
                "embeddings": anchor_embeddings,
            }

        self._is_initialized = True
        logger.info("SemanticClassifier initialized with %d categories.", len(self._anchor_cache))

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentence chunks for granular evidence extraction."""
        # Split on sentence boundaries (. ! ?) while keeping meaningful text
        raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        sentences = [s.strip() for s in raw_sentences if s and len(s.strip()) > 3]
        return sentences if sentences else [text.strip()]

    def classify_text(
        self,
        text: str,
        threshold: Optional[float] = None,
    ) -> List[TacticMatch]:
        """Classify raw text against all 8 manipulation categories.

        Args:
            text: Transcript utterance to analyze.
            threshold: Optional custom cosine similarity cutoff (defaults to self.similarity_threshold).

        Returns:
            List of TacticMatch objects with category, confidence, evidence text, and explanation.
        """
        if not text or not text.strip():
            return []

        if not self._is_initialized:
            self.initialize()

        effective_threshold = threshold if threshold is not None else self.similarity_threshold

        # We evaluate both individual sentences (for precise evidence) and the full text (for overall context)
        sentences = self._split_into_sentences(text)
        candidates = list(dict.fromkeys([text.strip()] + sentences))

        # Best match per category: category -> dict(confidence, evidence_text, best_anchor, definition)
        best_matches: Dict[ManipulationCategory, Dict[str, Any]] = {}

        for candidate in candidates:
            candidate_emb = self.embedding_engine.embed_text(candidate)

            for category, cache in self._anchor_cache.items():
                anchor_embeddings = cache["embeddings"]
                # Vectorized dot product (since embeddings are normalized, dot product == cosine similarity)
                similarities = np.dot(anchor_embeddings, candidate_emb)
                max_idx = int(np.argmax(similarities))
                max_sim = float(similarities[max_idx])

                if max_sim >= effective_threshold:
                    current_best = best_matches.get(category)
                    if current_best is None or max_sim > current_best["confidence"]:
                        best_matches[category] = {
                            "confidence": max_sim,
                            "evidence_text": candidate,
                            "best_anchor": cache["texts"][max_idx],
                            "definition": cache["definition"],
                        }

        results: List[TacticMatch] = []
        for category, match in best_matches.items():
            tactic_def: TacticDefinition = match["definition"]
            sim_score = match["confidence"]
            results.append(
                TacticMatch(
                    tactic=category,
                    confidence=round(sim_score, 3),
                    evidence_text=match["evidence_text"],
                    explanation=(
                        f"Semantic match to '{tactic_def.name}' "
                        f"(anchor: '{match['best_anchor']}') with cosine similarity {sim_score:.2f}"
                    ),
                    description=tactic_def.description,
                )
            )

        # Sort matches by confidence descending
        results.sort(key=lambda m: m.confidence, reverse=True)
        return results

    def classify_segment(
        self,
        segment: TranscriptSegment,
        threshold: Optional[float] = None,
    ) -> List[TacticMatch]:
        """Classify a TranscriptSegment against manipulation categories."""
        return self.classify_text(segment.text, threshold=threshold)


# Global singleton instance
semantic_classifier = SemanticClassifier()
