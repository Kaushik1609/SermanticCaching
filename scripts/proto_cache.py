"""CacheIQ In-Memory Prototype Cache (Phase P1).

Demonstrates cosine similarity lookup via dot product of L2-normalised vectors
and evaluates 8 sample benchmark pairs against the T_HIT threshold.
"""

import sys
from pathlib import Path

# Add project root to sys.path so backend modules can be imported directly
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from typing import List, Tuple, Optional
import numpy as np

from backend.engine.embedding.embedder import (
    embed,
    cosine_similarity,
    warm_up,
    EMBEDDING_MODEL_NAME,
)

# Benchmark pairs (PRD §5.2 categories: paraphrase vs related_different / numeric)
SAMPLE_PAIRS = [
    # Paraphrases (Expected: High similarity >= 0.85 -> HIT)
    (
        "What is machine learning?",
        "Explain machine learning.",
        "paraphrase",
        "Machine learning is a field of AI where models learn patterns from data.",
    ),
    (
        "How does backpropagation work?",
        "Explain backpropagation in neural networks.",
        "paraphrase",
        "Backpropagation computes gradients via the chain rule to update weights.",
    ),
    (
        "What is the capital of France?",
        "Tell me the capital city of France.",
        "paraphrase",
        "The capital of France is Paris.",
    ),
    (
        "How to reverse a linked list in Python?",
        "Reverse linked list Python code",
        "paraphrase",
        "Iteratively adjust next pointers: curr.next, prev, curr = prev, curr, curr.next.",
    ),
    # Related but different (Expected: Lower similarity or different meaning -> MISS)
    (
        "What is Python?",
        "What is the latest Python version?",
        "related_different",
        "Python is a high-level general-purpose programming language.",
    ),
    (
        "Top 5 programming languages in 2024",
        "Top 10 programming languages in 2024",
        "numeric",
        "Top 5 languages include Python, JavaScript, Java, C++, and C#.",
    ),
    (
        "What is the capital of France?",
        "What is the capital of Germany?",
        "related_different",
        "The capital of France is Paris.",
    ),
    (
        "How to sort a list in Python?",
        "How to reverse a linked list in Python?",
        "related_different",
        "Use sorted(my_list) or my_list.sort() in Python.",
    ),
]


class InMemoryProtoCache:
    """Simple in-memory semantic cache using L2-normalised embeddings."""

    def __init__(self, t_hit: float = 0.85):
        self.t_hit = t_hit
        # List of (query_text, embedding_vector, cached_response)
        self.entries: List[Tuple[str, np.ndarray, str]] = []

    def store(self, query: str, response: str) -> None:
        """Embed and store a query and response."""
        vector = embed(query)
        self.entries.append((query, vector, response))

    def lookup(self, query: str) -> Tuple[Optional[str], float, Optional[str]]:
        """Look up nearest neighbor using dot-product similarity.

        Returns (best_response, best_similarity, best_matched_query).
        """
        if not self.entries:
            return None, 0.0, None

        q_vec = embed(query)
        best_sim = -1.0
        best_response = None
        best_matched_query = None

        for stored_query, stored_vec, response in self.entries:
            # For unit vectors, cosine similarity is exactly the dot product
            sim = cosine_similarity(q_vec, stored_vec)
            if sim > best_sim:
                best_sim = sim
                best_response = response
                best_matched_query = stored_query

        return best_response, best_sim, best_matched_query


def run_prototype_benchmark(t_hit: float = 0.85):
    print("=" * 80)
    print(f"CacheIQ In-Memory Semantic Cache Prototype (Model: {EMBEDDING_MODEL_NAME})")
    print(f"Similarity Threshold T_HIT = {t_hit:.2f}")
    print("=" * 80)
    print(f"{'#':<3} | {'Stored Query / Probe Query':<52} | {'Sim':<6} | {'Status':<6} | {'Expected'}")
    print("-" * 80)

    cache = InMemoryProtoCache(t_hit=t_hit)

    for i, (q_stored, q_probe, category, sample_ans) in enumerate(SAMPLE_PAIRS, 1):
        # Store initial query
        cache.entries.clear()
        cache.store(q_stored, sample_ans)

        # Probe with second query
        _, sim, matched = cache.lookup(q_probe)
        is_hit = sim >= t_hit
        status = "HIT" if is_hit else "MISS"
        expected = "HIT" if category == "paraphrase" else "MISS"

        flag = "[OK]" if status == expected else "[FAIL]"

        print(f"{i:<3} | Stored: {q_stored}")
        print(f"    | Probe:  {q_probe}")
        print(f"    | Sim: {sim:.4f}  Result: {status:<4}  Expected: {expected:<4}  Cat: {category:<17} {flag}")
        print("-" * 80)


if __name__ == "__main__":
    print("Warming up embedding model...")
    warm_up()
    print("Warm-up complete.\n")
    run_prototype_benchmark(t_hit=0.85)
