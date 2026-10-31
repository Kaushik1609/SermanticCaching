"""Tests for Persistent Store (backend/engine/store/repo.py).

Verifies:
- Insert and exact lookup
- Top-K semantic ordering
- Context key isolation (A vs B)
- Invalidation lifecycle
- Unique exact_key among ACTIVE rows
- Query log appending
"""

import hashlib
import numpy as np
import pytest
import psycopg
from datetime import datetime, timezone, timedelta

from backend.app import config
from backend.engine.embedding.embedder import embed
from backend.engine.store import repo


def is_db_reachable() -> bool:
    """Quick check to see if PostgreSQL is reachable."""
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=1) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not is_db_reachable(),
    reason="PostgreSQL not running. Start Docker Postgres ('docker compose up -d') to run DB integration tests."
)


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure clean tables before each integration test."""
    repo.reset_all()
    yield
    repo.reset_all()


def compute_test_exact_key(query: str, context_key: str = "default", config_hash: str = "hash123") -> str:
    raw = f"{query.lower().strip()}|{context_key}|{config_hash}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def test_insert_and_exact_lookup():
    """Insert entry and verify get_by_exact_key retrieves it with correct fields."""
    query = "What is machine learning?"
    exact_key = compute_test_exact_key(query)
    emb = embed(query)

    entry_id = repo.insert_entry(
        context_key="default",
        query_text=query,
        exact_key=exact_key,
        query_embedding=emb,
        response_text="Machine learning is pattern learning from data.",
        embedding_model="all-MiniLM-L6-v2",
        config_hash="hash123",
        prompt_tokens=10,
        completion_tokens=20,
    )
    assert entry_id > 0

    found = repo.get_by_exact_key(exact_key, context_key="default")
    assert found is not None
    assert found["id"] == entry_id
    assert found["query_text"] == query
    assert found["response_text"] == "Machine learning is pattern learning from data."
    assert found["hit_count"] == 0
    assert found["status"] == "ACTIVE"


def test_top_k_ordering():
    """Insert 5 entries and verify search_top_k orders them by cosine similarity descending."""
    base_query = "What is machine learning?"
    candidates = [
        "What is machine learning in simple terms?",
        "Explain machine learning algorithms.",
        "How do computers learn from data?",
        "Introduction to artificial intelligence.",
        "How to cook chocolate chip cookies?",
    ]

    for c in candidates:
        key = compute_test_exact_key(c)
        repo.insert_entry(
            context_key="default",
            query_text=c,
            exact_key=key,
            query_embedding=embed(c),
            response_text=f"Answer for {c}",
            embedding_model="all-MiniLM-L6-v2",
            config_hash="hash123",
        )

    results = repo.search_top_k(embed(base_query), context_key="default", k=5)
    assert len(results) == 5

    # Check similarities are in descending order
    similarities = [r["similarity"] for r in results]
    assert similarities == sorted(similarities, reverse=True)

    # Top candidate should be the closest paraphrase
    assert "simple terms" in results[0]["query_text"]
    # Last candidate should be the cooking query
    assert "cookies" in results[-1]["query_text"]


def test_context_key_isolation():
    """Entries stored in context A must NEVER be returned for context B."""
    query = "Explain gradient descent."
    key_a = compute_test_exact_key(query, context_key="tenant_a")
    emb = embed(query)

    repo.insert_entry(
        context_key="tenant_a",
        query_text=query,
        exact_key=key_a,
        query_embedding=emb,
        response_text="Gradient descent optimizes loss.",
        embedding_model="all-MiniLM-L6-v2",
        config_hash="hash123",
    )

    # Lookup by exact key in tenant_b -> None
    found_b = repo.get_by_exact_key(key_a, context_key="tenant_b")
    assert found_b is None

    # Search top-k in tenant_b -> empty
    results_b = repo.search_top_k(emb, context_key="tenant_b", k=5)
    assert len(results_b) == 0

    # Search top-k in tenant_a -> found
    results_a = repo.search_top_k(emb, context_key="tenant_a", k=5)
    assert len(results_a) == 1
    assert results_a[0]["query_text"] == query


def test_invalidated_entries_filtered():
    """INVALIDATED entries must be excluded from active searches."""
    query = "What is backpropagation?"
    key = compute_test_exact_key(query)
    emb = embed(query)

    entry_id = repo.insert_entry(
        context_key="default",
        query_text=query,
        exact_key=key,
        query_embedding=emb,
        response_text="Backpropagation computes gradients.",
        embedding_model="all-MiniLM-L6-v2",
        config_hash="hash123",
    )

    # Invalidate
    ok = repo.invalidate(entry_id)
    assert ok is True

    # Exact lookup should not return invalidated entry
    found = repo.get_by_exact_key(key, context_key="default")
    assert found is None

    # Top-K should not return invalidated entry
    results = repo.search_top_k(emb, context_key="default", k=5)
    assert len(results) == 0


def test_unique_exact_key_active():
    """Attempting to insert a duplicate active exact_key should raise an integrity error."""
    import psycopg

    query = "How to sort a list?"
    key = compute_test_exact_key(query)
    emb = embed(query)

    repo.insert_entry(
        context_key="default",
        query_text=query,
        exact_key=key,
        query_embedding=emb,
        response_text="Use sorted().",
        embedding_model="all-MiniLM-L6-v2",
        config_hash="hash123",
    )

    # Second insert with identical exact_key should trigger unique constraint
    with pytest.raises(psycopg.errors.UniqueViolation):
        repo.insert_entry(
            context_key="default",
            query_text=query,
            exact_key=key,
            query_embedding=emb,
            response_text="Use sorted() again.",
            embedding_model="all-MiniLM-L6-v2",
            config_hash="hash123",
        )


def test_hit_increment_and_log():
    """Verify hit counter increment and query logging."""
    query = "What is Docker?"
    key = compute_test_exact_key(query)
    entry_id = repo.insert_entry(
        context_key="default",
        query_text=query,
        exact_key=key,
        query_embedding=embed(query),
        response_text="Docker runs containers.",
        embedding_model="all-MiniLM-L6-v2",
        config_hash="hash123",
    )

    repo.increment_hit(entry_id)
    repo.increment_hit(entry_id)

    entry = repo.get_by_exact_key(key, context_key="default")
    assert entry["hit_count"] == 2

    log_id = repo.log_query(
        context_key="default",
        strategy="semantic_verified",
        outcome="HIT",
        reason_code="HIT_SEMANTIC",
        similarity=0.92,
        lookup_ms=18.5,
        total_ms=19.0,
        llm_called=False,
        prompt_tokens=15,
        completion_tokens=25,
        matched_entry_id=entry_id,
    )
    assert log_id > 0

