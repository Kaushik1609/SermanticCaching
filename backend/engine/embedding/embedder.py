"""CacheIQ Embedding Engine.

Math in plain words:
- An embedding is a vector of 384 floating-point numbers placing text as a point/arrow in space.
- Similar meaning means the arrows point in nearly the same direction.
- Cosine similarity measures the angle between two vectors:
      cosine_similarity(a, b) = (a · b) / (||a|| * ||b||)
- If both vectors are L2-normalised (scaled to length 1, so ||a|| = ||b|| = 1),
  cosine similarity simplifies to the dot product:
      cosine_similarity(a, b) = a · b = sum(a[i] * b[i])
- pgvector's `<=>` operator computes cosine distance = 1 - cosine_similarity.
  Therefore, similarity = 1 - (a <=> b).
"""

from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

# Frozen model constant per PRD §3
EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM: int = 384

# Module-level singleton
_model: Optional[SentenceTransformer] = None


def get_model() -> SentenceTransformer:
    """Load the SentenceTransformer model once as a singleton."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed(text: str) -> np.ndarray:
    """Generate an L2-normalised 384-dimensional embedding for a single text.

    Normalised so that ||v||_2 = 1.0, enabling cosine similarity via dot product.
    """
    model = get_model()
    # normalize_embeddings=True ensures output vector has unit length
    vec = model.encode(text, normalize_embeddings=True)
    return np.asarray(vec, dtype=np.float32)


def embed_many(texts: List[str]) -> List[np.ndarray]:
    """Batch embed multiple texts with L2-normalisation."""
    if not texts:
        return []
    model = get_model()
    vecs = model.encode(texts, normalize_embeddings=True)
    return [np.asarray(v, dtype=np.float32) for v in vecs]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two L2-normalised unit vectors.

    Because vectors are normalised (length 1), cosine similarity is identical
    to their dot product: dot(a, b).
    """
    return float(np.dot(a, b))


def warm_up() -> None:
    """Preload model weights into memory at startup to avoid cold-start latency."""
    embed("warm up")

