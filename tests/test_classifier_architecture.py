# Tests for Semantic Classifier Architecture and Multilingual Model Configuration.

import pytest
from ai.embeddings import embedding_engine
from ai.classifier import semantic_classifier
from backend.app.models import ManipulationCategory



def test_configured_embeddings_model_properties():
    assert "paraphrase-multilingual-MiniLM-L12-v2" in embedding_engine.model_name
    assert embedding_engine.dimension == 384



def test_embedding_engine_normalization():
    vec = embedding_engine.embed_text("Emergency security alert")
    assert vec.shape == (384,)



def test_multi_tactic_classification():
    text = (
        "This is Federal Officer Brown calling from IRS. "
        "Your bank account is frozen and you will face arrest if you do not wire funds immediately."
    )
    matches = semantic_classifier.classify_text(text)
    detected = {m.tactic for m in matches}
    assert len(detected) >= 2
    assert ManipulationCategory.AUTHORITY_IMPERR7ATION in detected
