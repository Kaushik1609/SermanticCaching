"""CacheIQ Demo Seeder (Phase P6).

Cleans the cache and preloads 10 diverse benchmark entries for instant, zero-latency live demos.
"""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.app import config
from backend.engine.embedding.embedder import embed, warm_up
from backend.engine.search.normalizer import normalize, compute_exact_key, compute_config_hash
from backend.engine.store import repo

DEMO_ENTRIES = [
    {
        "query": "What is machine learning in simple terms?",
        "answer": (
            "Machine learning is a field of artificial intelligence where algorithms learn patterns "
            "from data to make decisions or predictions, rather than being explicitly programmed with rigid rules."
        ),
        "prompt_tokens": 38,
        "completion_tokens": 34,
    },
    {
        "query": "How does backpropagation work?",
        "answer": (
            "Backpropagation computes the gradient of the loss function with respect to each weight using "
            "the chain rule, propagating errors backwards through layers to update network weights via gradient descent."
        ),
        "prompt_tokens": 42,
        "completion_tokens": 39,
    },
    {
        "query": "What is semantic caching for LLM applications?",
        "answer": (
            "Semantic caching stores previously generated LLM answers indexed by high-dimensional embedding vectors, "
            "allowing semantically equivalent prompts to be answered in sub-20ms without invoking the upstream model."
        ),
        "prompt_tokens": 40,
        "completion_tokens": 41,
    },
    {
        "query": "Explain gradient descent optimization.",
        "answer": (
            "Gradient descent iteratively updates parameters in the direction of the steepest descent of the loss surface, "
            "scaled by a learning rate hyperparameter until convergence."
        ),
        "prompt_tokens": 35,
        "completion_tokens": 32,
    },
    {
        "query": "What is the capital of France?",
        "answer": "The capital of France is Paris.",
        "prompt_tokens": 15,
        "completion_tokens": 12,
    },
    {
        "query": "How to reverse a linked list in Python?",
        "answer": (
            "To reverse a singly linked list in Python iteratively:\n"
            "prev = None\ncurr = head\nwhile curr:\n    nxt = curr.next\n    curr.next = prev\n    prev = curr\n    curr = nxt\nreturn prev"
        ),
        "prompt_tokens": 32,
        "completion_tokens": 45,
    },
    {
        "query": "Explain transformer architecture in NLP.",
        "answer": (
            "The Transformer architecture relies entirely on multi-head self-attention mechanisms to model relationships "
            "between all tokens simultaneously, removing sequential recurrence and enabling massive parallel training."
        ),
        "prompt_tokens": 45,
        "completion_tokens": 42,
    },
    {
        "query": "What is the difference between precision and recall?",
        "answer": (
            "Precision measures the proportion of retrieved positives that are truly relevant (TP / (TP + FP)), "
            "while recall measures the proportion of all actual positives that were successfully retrieved (TP / (TP + FN))."
        ),
        "prompt_tokens": 36,
        "completion_tokens": 38,
    },
    {
        "query": "How do convolutional neural networks work?",
        "answer": (
            "CNNs apply learnable spatial filters (kernels) across input feature maps to capture translation-invariant patterns "
            "such as edges, textures, and hierarchical shapes."
        ),
        "prompt_tokens": 38,
        "completion_tokens": 35,
    },
    {
        "query": "What is Docker and how does containerization work?",
        "answer": (
            "Docker packages applications and their dependencies into standardized containers that share the host OS kernel, "
            "providing lightweight process isolation without the overhead of full virtual machines."
        ),
        "prompt_tokens": 35,
        "completion_tokens": 34,
    },
]


def seed():
    print("Warming up embedding model...")
    warm_up()

    config_hash = compute_config_hash("mock", "default", 0.0)

    try:
        print("Resetting existing cache and query logs...")
        repo.reset_all()

        print(f"Preloading {len(DEMO_ENTRIES)} demo entries...")
        for i, item in enumerate(DEMO_ENTRIES, 1):
            q_norm = normalize(item["query"])
            exact_key = compute_exact_key(q_norm, "default", config_hash)
            q_emb = embed(q_norm)

            entry_id = repo.insert_entry(
                context_key="default",
                query_text=q_norm,
                exact_key=exact_key,
                query_embedding=q_emb,
                response_text=item["answer"],
                embedding_model=config.EMBEDDING_MODEL,
                config_hash=config_hash,
                prompt_tokens=item["prompt_tokens"],
                completion_tokens=item["completion_tokens"],
            )

            # Preload a simulated HIT in query_log for telemetry demo
            repo.increment_hit(entry_id)
            repo.log_query(
                context_key="default",
                strategy="semantic_verified",
                outcome="HIT",
                reason_code="HIT_SEMANTIC",
                similarity=0.92,
                lookup_ms=18.4,
                total_ms=18.4,
                llm_called=False,
                prompt_tokens=item["prompt_tokens"],
                completion_tokens=item["completion_tokens"],
                matched_entry_id=entry_id,
            )

            print(f"  [{i}/10] Seeded: '{item['query']}' (ID: #{entry_id})")

        print("\nDemo seeding completed successfully! Cache is primed for live presentation.")
    except Exception as e:
        print(f"Note: Could not seed to database ({e}).")
        print("Ensure PostgreSQL is running via 'docker compose up -d' before seeding.")


if __name__ == "__main__":
    seed()

