from typing import List, Optional


class EmbeddingEngine:
    """Embedding engine stub for Phase 1.

    In Phase 2, this will load a lightweight Sentence Transformer model
    (e.g., all-MiniLM-L6-v2) for local, ultra-fast embedding computation
    without any external cloud LLM dependencies.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._is_loaded = False

    def load_model(self) -> None:
        """Load the local Sentence Transformer model into memory (Phase 2)."""
        # Phase 1 stub: no-op
        self._is_loaded = True

    def embed_text(self, text: str) -> List[float]:
        """Compute the embedding vector for a single text string."""
        if not self._is_loaded:
            self.load_model()
        # Phase 1 stub: returns empty list until Phase 2 model loading
        return []

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Compute embedding vectors for a batch of texts."""
        return [self.embed_text(t) for t in texts]


# Global singleton instance
embedding_engine = EmbeddingEngine()
