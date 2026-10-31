"""CacheIQ Repository (Persistent Store Operations).

Parameterised SQL only. No query text in logs.
Source of truth: docs/00_MAIN_PRD.md §4.1 and §6.1.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np

from backend.engine.store.db import get_db


def insert_entry(
    context_key: str,
    query_text: str,
    exact_key: str,
    query_embedding: np.ndarray,
    response_text: str,
    embedding_model: str,
    config_hash: str,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    expires_at: Optional[datetime] = None,
) -> int:
    """Insert a new cache entry. Returns the inserted entry id."""
    query = """
        INSERT INTO cache_entries (
            context_key, query_text, exact_key, query_embedding, response_text,
            embedding_model, config_hash, prompt_tokens, completion_tokens, expires_at
        )
        VALUES (
            %(context_key)s, %(query_text)s, %(exact_key)s, %(query_embedding)s, %(response_text)s,
            %(embedding_model)s, %(config_hash)s, %(prompt_tokens)s, %(completion_tokens)s, %(expires_at)s
        )
        RETURNING id;
    """
    params = {
        "context_key": context_key,
        "query_text": query_text,
        "exact_key": exact_key,
        "query_embedding": query_embedding,
        "response_text": response_text,
        "embedding_model": embedding_model,
        "config_hash": config_hash,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "expires_at": expires_at,
    }
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            conn.commit()
            return row["id"]


def get_by_exact_key(exact_key: str, context_key: str = "default") -> Optional[Dict[str, Any]]:
    """Lookup an ACTIVE cache entry by its exact_key within a given context."""
    query = """
        SELECT id, context_key, query_text, exact_key, response_text,
               embedding_model, config_hash, expires_at, hit_count, status
        FROM cache_entries
        WHERE exact_key = %(exact_key)s
          AND context_key = %(context_key)s
          AND status = 'ACTIVE'
        LIMIT 1;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, {"exact_key": exact_key, "context_key": context_key})
            return cur.fetchone()


def search_top_k(
    embedding: np.ndarray,
    context_key: str = "default",
    k: int = 5,
) -> List[Dict[str, Any]]:
    """Top-K semantic search using pgvector cosine distance.

    Uses EXACTLY the SQL specification from PRD §4.1:
    similarity = 1 - (query_embedding <=> %(q)s)
    """
    query = """
        SELECT id, query_text, response_text, embedding_model, config_hash, expires_at,
               1 - (query_embedding <=> %(q)s) AS similarity
        FROM cache_entries
        WHERE context_key = %(ctx)s AND status = 'ACTIVE'
        ORDER BY query_embedding <=> %(q)s
        LIMIT %(k)s;
    """
    params = {
        "q": embedding,
        "ctx": context_key,
        "k": k,
    }
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def increment_hit(entry_id: int) -> None:
    """Atomically increment the hit counter for a cache entry."""
    query = """
        UPDATE cache_entries
        SET hit_count = hit_count + 1
        WHERE id = %(id)s;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, {"id": entry_id})
            conn.commit()


def invalidate(entry_id: int) -> bool:
    """Mark a cache entry as INVALIDATED."""
    query = """
        UPDATE cache_entries
        SET status = 'INVALIDATED'
        WHERE id = %(id)s AND status = 'ACTIVE'
        RETURNING id;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, {"id": entry_id})
            row = cur.fetchone()
            conn.commit()
            return row is not None


def list_entries(limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """List cache entries with pagination and total count."""
    count_query = "SELECT COUNT(*) AS total FROM cache_entries;"
    list_query = """
        SELECT id, query_text, created_at, expires_at, hit_count, status, context_key
        FROM cache_entries
        ORDER BY id DESC
        LIMIT %(limit)s OFFSET %(offset)s;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(count_query)
            total = cur.fetchone()["total"]

            cur.execute(list_query, {"limit": limit, "offset": offset})
            items = cur.fetchall()
            return items, total


def count(context_key: Optional[str] = None, status: str = "ACTIVE") -> int:
    """Count cache entries matching context and status."""
    if context_key:
        query = "SELECT COUNT(*) AS c FROM cache_entries WHERE context_key = %(ctx)s AND status = %(status)s;"
        params = {"ctx": context_key, "status": status}
    else:
        query = "SELECT COUNT(*) AS c FROM cache_entries WHERE status = %(status)s;"
        params = {"status": status}

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()["c"]


def log_query(
    context_key: str,
    strategy: str,
    outcome: str,
    reason_code: str,
    similarity: Optional[float],
    lookup_ms: Optional[float],
    total_ms: Optional[float],
    llm_called: bool,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    matched_entry_id: Optional[int] = None,
) -> int:
    """Append a row to query_log. Note: Never stores query_text for privacy."""
    query = """
        INSERT INTO query_log (
            context_key, strategy, outcome, reason_code, similarity,
            lookup_ms, total_ms, llm_called, prompt_tokens, completion_tokens, matched_entry_id
        )
        VALUES (
            %(context_key)s, %(strategy)s, %(outcome)s, %(reason_code)s, %(similarity)s,
            %(lookup_ms)s, %(total_ms)s, %(llm_called)s, %(prompt_tokens)s, %(completion_tokens)s, %(matched_entry_id)s
        )
        RETURNING id;
    """
    params = {
        "context_key": context_key,
        "strategy": strategy,
        "outcome": outcome,
        "reason_code": reason_code,
        "similarity": similarity,
        "lookup_ms": lookup_ms,
        "total_ms": total_ms,
        "llm_called": llm_called,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "matched_entry_id": matched_entry_id,
    }
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            conn.commit()
            return row["id"]


def reset_all() -> None:
    """Clear all cache entries and query logs for a fresh demo run."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE query_log, cache_entries RESTART IDENTITY CASCADE;")
            conn.commit()


def cleanup_context_prefix(prefix: str) -> None:
    """Delete all cache entries and query logs matching a context_key prefix."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM query_log WHERE context_key LIKE %(pattern)s;", {"pattern": f"{prefix}%"})
            cur.execute("DELETE FROM cache_entries WHERE context_key LIKE %(pattern)s;", {"pattern": f"{prefix}%"})
            conn.commit()


