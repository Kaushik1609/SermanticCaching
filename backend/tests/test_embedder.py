"""Unit tests for the embedding engine and similarity math."""

import numpy as np
import pytest
from backend.engine.embedding.embedder import (
    embed,
    embed_many,
    cosine_similarity,
    warm_up,
    EMBEDDING_DIM,
)


@pytest.fixture(scope="module", autouse=True)
def preload():
    """Ensure model is loaded once before running tests."""
    warm_up()


def test_embedding_dimensions_and_norm():
    """Embeddings must be 384-dimensional and strictly L2-normalised to length 1."""
    text = "Explain machine learning in simple terms."
    vec = embed(text)

    assert isinstance(vec, np.ndarray)
    assert vec.shape == (EMBEDDING_DIM,)
    assert vec.dtype == np.float32

    # L2 norm must be 1.0 within float tolerance
    norm = np.linalg.norm(vec)
    assert np.isclose(norm, 1.0, atol=1e-5)


def test_identical_text_similarity():
    """Identical sentences must have cosine similarity approximately 1.0."""
    t1 = "What is semantic caching?"
    t2 = "What is semantic caching?"
    v1 = embed(t1)
    v2 = embed(t2)

    sim = cosine_similarity(v1, v2)
    assert np.isclose(sim, 1.0, atol=1e-4)


def test_paraphrase_similarity_above_threshold():
    """Clear paraphrases must score above 0.80."""
    p1 = "What is machine learning?"
    p2 = "Explain machine learning."
    v1 = embed(p1)
    v2 = embed(p2)

    sim = cosine_similarity(v1, v2)
    assert sim > 0.80, f"Expected paraphrase similarity > 0.80, got {sim}"


def test_unrelated_text_similarity_below_threshold():
    """Unrelated sentences must score well below 0.40."""
    t1 = "What is the capital of France?"
    t2 = "How do you cook chocolate chip cookies?"
    v1 = embed(t1)
    v2 = embed(t2)

    sim = cosine_similarity(v1, v2)
    assert sim < 0.40, f"Expected unrelated similarity < 0.40, got {sim}"


def test_embed_many_batch():
    """embed_many must return matching batch results with unit norms."""
    texts = [
        "First test query",
        "Second query about vectors",
        "Third query about PostgreSQL",
    ]
    vectors = embed_many(texts)

    assert len(vectors) == 3
    for v in vectors:
        assert v.shape == (EMBEDDING_DIM,)
        assert np.isclose(np.linalg.norm(v), 1.0, atol=1e-5)

    # Comparing individual embed with batch embed
    single_v0 = embed(texts[0])
    assert np.allclose(vectors[0], single_v0, atol=1e-4)

