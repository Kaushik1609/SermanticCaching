"""CacheIQ Lookup Latency Benchmark (Live PostgreSQL / pgvector HNSW Index).

Preloads 1k and 10k synthetic entries into real Postgres with the HNSW index (fixed seed),
then measures the FULL lookup path (normalize + embed + search + verify) over 200 queries.
Reports mean and p95 latency and saves data/results/latency.json stating the hardware.
"""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import json
import time
import os
import platform
from datetime import datetime, timezone
import numpy as np

from backend.app import config
from backend.engine.embedding.embedder import embed, warm_up
from backend.engine.search.normalizer import normalize, compute_exact_key, compute_config_hash
from backend.engine.store.db import get_db
from backend.engine.store import repo
from backend.engine.verifier.verifier import verify

RESULTS_DIR = root_dir / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LATENCY_FILE = RESULTS_DIR / "latency.json"


def get_hardware_info() -> dict:
    """Collect host hardware and environment specifications."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count_logical": os.cpu_count(),
        "python_version": platform.python_version(),
    }


def preload_synthetic_entries(n_entries: int, context_key: str, seed: int = 42) -> None:
    """Preload n_entries synthetic records into Postgres with normalized embeddings."""
    print(f"Preloading {n_entries:,} synthetic entries into PostgreSQL (context: {context_key})...")
    rng = np.random.default_rng(seed)
    config_hash = compute_config_hash("mock", "default", 0.0)

    # Clean existing rows for this context
    repo.cleanup_context_prefix(context_key)

    # Generate unit vectors (384-d)
    raw = rng.standard_normal((n_entries, 384), dtype=np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    unit_vecs = raw / norms

    batch_size = 500
    rows_to_insert = []

    for i in range(n_entries):
        q_text = f"Synthetic benchmark knowledge entry {i} for machine learning scale testing"
        exact_k = compute_exact_key(q_text.lower(), context_key, config_hash)
        emb_list = unit_vecs[i].tolist()
        resp_text = f"Cached benchmark answer payload for entry {i}."
        rows_to_insert.append((
            context_key,
            q_text,
            exact_k,
            emb_list,
            resp_text,
            config.EMBEDDING_MODEL,
            config_hash,
            15,
            35,
        ))

    insert_sql = """
        INSERT INTO cache_entries (
            context_key, query_text, exact_key, query_embedding, response_text,
            embedding_model, config_hash, prompt_tokens, completion_tokens
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """

    with get_db() as conn:
        with conn.cursor() as cur:
            for start_idx in range(0, n_entries, batch_size):
                batch = rows_to_insert[start_idx : start_idx + batch_size]
                cur.executemany(insert_sql, batch)
        conn.commit()

    print(f"Preloaded {n_entries:,} entries into PostgreSQL successfully.")


def run_benchmark_scale(n_entries: int, n_queries: int = 200, seed: int = 42) -> dict:
    context_key = f"bench:{n_entries}"
    preload_synthetic_entries(n_entries, context_key=context_key, seed=seed)

    config_hash = compute_config_hash("mock", "default", 0.0)
    now_utc = datetime.now(timezone.utc)

    # 200 test probe queries
    queries = [
        f"Benchmark probe query number {i} evaluating semantic cache latency and retrieval"
        for i in range(n_queries)
    ]

    # Warm-up run
    warm_up()
    _ = repo.search_top_k(embed(queries[0]), context_key=context_key, k=5)

    print(f"Timing full lookup path (normalize + embed + search + verify) over {n_queries} queries...")
    latencies_ms = []

    for q in queries:
        t0 = time.perf_counter()

        # 1. Normalize
        norm_q = normalize(q)
        exact_key = compute_exact_key(norm_q, context_key, config_hash)

        # 2. Exact match check
        exact_hit = repo.get_by_exact_key(exact_key, context_key=context_key)

        # 3. Embed
        q_emb = embed(norm_q)

        # 4. Search top-K in Postgres HNSW index
        candidates = repo.search_top_k(q_emb, context_key=context_key, k=5)

        # 5. Verify candidates in rank order
        if candidates and float(candidates[0]["similarity"]) >= config.T_HIT:
            for cand in candidates:
                if float(cand["similarity"]) < config.T_HIT:
                    break
                v = verify(
                    new_query=norm_q,
                    candidate=cand,
                    request_config_hash=config_hash,
                    now=now_utc,
                    current_model=config.EMBEDDING_MODEL,
                )
                if v.ok:
                    break

        # Stop timer: Full lookup path complete
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

    # Clean up entries
    repo.cleanup_context_prefix(context_key)

    mean_ms = round(float(np.mean(latencies_ms)), 2)
    p95_ms = round(float(np.percentile(latencies_ms, 95)), 2)
    p99_ms = round(float(np.percentile(latencies_ms, 99)), 2)

    return {
        "entries_count": n_entries,
        "queries_tested": n_queries,
        "mean_lookup_ms": mean_ms,
        "p95_lookup_ms": p95_ms,
        "p99_lookup_ms": p99_ms,
    }


def main():
    print("=" * 80)
    print("CacheIQ Lookup Latency Benchmark (Live PostgreSQL HNSW Index)")
    print("=" * 80)

    hardware = get_hardware_info()
    print("Hardware:", json.dumps(hardware, indent=2))

    res_1k = run_benchmark_scale(n_entries=1_000, n_queries=200, seed=42)
    print(f"\n1k Scale  -> Mean: {res_1k['mean_lookup_ms']} ms | p95: {res_1k['p95_lookup_ms']} ms | p99: {res_1k['p99_lookup_ms']} ms")

    res_10k = run_benchmark_scale(n_entries=10_000, n_queries=200, seed=42)
    print(f"\n10k Scale -> Mean: {res_10k['mean_lookup_ms']} ms | p95: {res_10k['p95_lookup_ms']} ms | p99: {res_10k['p99_lookup_ms']} ms")

    output = {
        "benchmark_date": "2026-10-31",
        "database": "PostgreSQL 16 with pgvector",
        "index_type": "HNSW (vector_cosine_ops)",
        "dimension": 384,
        "hardware": hardware,
        "scales": {
            "1k": res_1k,
            "10k": res_10k,
        },
    }

    with open(LATENCY_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"\nLatency benchmark saved to: {LATENCY_FILE}")


if __name__ == "__main__":
    main()
