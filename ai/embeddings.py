import logging
from typing import List, Optional
import numpy as np

logger = logging.getLogger("raksha.ai.embeddings")


class EmbeddingEngine:
    """Local Sentence Transformer embedding engine for RAKSHA.

    Loads a lightweight, publicly available multilingual Sentence Transformer model
    (default: 'paraphrase-multilingual-MiniLM-L12-v2') locally into memory once.
    Fails gracefully with a clear error message if the model cannot be loaded.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self.model_name = model_name
        self._model = None
        self._is_loaded = False
        self._dimension: Optional[int] = None

    def load_model(self) -> None:
        """Load the local Sentence Transformer model into memory once."""
        if self._is_loaded and self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as err:
            raise RuntimeError(
                "The 'sentence-transformers' package is required for RAKSHA's semantic detector. "
                "Please install it using: pip install sentence-transformers"
            ) from err

        try:
            logger.info("Loading SentenceTransformer model '%s'...", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            self._is_loaded = True
            if hasattr(self._model, "get_sentence_embedding_dimension"):
                self._dimension = self._model.get_sentence_embedding_dimension()
            logger.info("SentenceTransformer model '%s' loaded successfully.", self.model_name)
        except Exception as exc:
            self._is_loaded = False
            self._model = None
            raise RuntimeError(
                f"Failed to load or download SentenceTransformer model '{self.model_name}'. "
                f"Ensure internet connectivity for initial download or pre-cache the model locally. "
                f"Original error: {exc}"
            ) from exc

    @property
    def dimension(self) -> int:
        """Get the embedding vector dimension dynamically."""
        if self._dimension is not None:
            return self._dimension
        if self._is_loaded and self._model is not None and hasattr(self._model, "get_sentence_embedding_dimension"):
            self._dimension = self._model.get_sentence_embedding_dimension()
            return self._dimension
        return 384  # Sensible fallback prior to model initialization

    def embed_text(self, text: str) -> np.ndarray:
        """Compute a normalized 1D embedding vector for a single text string."""
        if not text or not text.strip():
            return np.zeros(self.dimension, dtype=np.float32)

        if not self._is_loaded:
            self.load_model()

        embedding = self._model.encode(
            text.strip(),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if self._dimension is None and hasattr(embedding, "shape") and len(embedding.shape) > 0:
            self._dimension = int(embedding.shape[-1])
        return embedding

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Compute normalized 2D embedding vectors for a batch of text strings."""
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        if not self._is_loaded:
            self.load_model()

        cleaned_texts = [t.strip() if t and t.strip() else "" for t in texts]
        embeddings = self._model.encode(
            cleaned_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if self._dimension is None and hasattr(embeddings, "shape") and len(embeddings.shape) > 1:
            self._dimension = int(embeddings.shape[1])
        return embeddings

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded


# Global singleton instance
embedding_engine = EmbeddingEngine()
