"""In-memory Arena Runner (Reference Implementation).

Kept under tests/ as a reference implementation per PRD v2.0 requirements.
Does not touch PostgreSQL or pgvector; evaluates similarity via NumPy dot products.
"""

from typing import List, Dict, Any
import numpy as np
import time

from backend.app import config
from backend.app.models import ArenaRow
from backend.engine.embedding.embedder import embed, cosine_similarity
from backend.engine.search.normalizer import normalize, compute_exact_key, compute_config_hash
from backend.engine.verifier.time_sensitive import is_time_sensitive
from backend.engine.verifier.verifier import verify


class InProcessArenaRunner:
    """In-memory reference evaluator running strategies directly in-process."""

    def __init__(self, t_hit: float = config.T_HIT, t_low: float = config.T_LOW):
        self.t_hit = t_hit
        self.t_low = t_low
        self.config_hash = compute_config_hash("mock", "default", 0.0)

    def evaluate_strategy(self, strat_name: str, pairs: List[Dict[str, Any]]) -> ArenaRow:
        total = len(pairs)
        if total == 0:
            return ArenaRow(
                strategy=strat_name,
                hit_rate=0.0,
                precision=None,
                false_hit_rate=None,
                recall_same=0.0,
                avg_lookup_ms=0.0,
                p95_lookup_ms=0.0,
                llm_calls_avoided=0,
                est_cost_saved=0.0,
            )

        hits = 0
        correct_hits = 0
        false_hits = 0
        same_count = sum(1 for p in pairs if p.get("label") == "same")
        lookup_times = []

        for p in pairs:
            q_a = p["query_a"]
            q_b = p["query_b"]
            is_same = (p.get("label") == "same")

            norm_a = normalize(q_a)
            exact_key_a = compute_exact_key(norm_a, "arena", self.config_hash)
            emb_a = embed(norm_a)

            t0 = time.perf_counter()
            norm_b = normalize(q_b)
            exact_key_b = compute_exact_key(norm_b, "arena", self.config_hash)

            is_hit = False

            if strat_name == "no_cache":
                is_hit = False
                t_lookup = 0.0

            elif strat_name == "exact_match":
                t_lookup = (time.perf_counter() - t0) * 1000.0
                is_hit = (exact_key_a == exact_key_b)

            elif strat_name == "semantic_raw":
                emb_b = embed(norm_b)
                sim = cosine_similarity(emb_b, emb_a)
                t_lookup = (time.perf_counter() - t0) * 1000.0
                is_hit = (exact_key_a == exact_key_b) or (sim >= self.t_hit)

            elif strat_name == "semantic_verified":
                is_ts_b = is_time_sensitive(norm_b)
                if is_ts_b:
                    is_hit = False
                elif exact_key_a == exact_key_b:
                    is_hit = True
                else:
                    emb_b = embed(norm_b)
                    sim = cosine_similarity(emb_b, emb_a)
                    if sim >= self.t_hit:
                        candidate = {
                            "query_text": norm_a,
                            "expires_at": None,
                            "config_hash": self.config_hash,
                            "embedding_model": config.EMBEDDING_MODEL,
                        }
                        from datetime import datetime, timezone
                        verdict = verify(
                            new_query=norm_b,
                            candidate=candidate,
                            request_config_hash=self.config_hash,
                            now=datetime.now(timezone.utc),
                            current_model=config.EMBEDDING_MODEL,
                        )
                        is_hit = verdict.ok
                    else:
                        is_hit = False
                t_lookup = (time.perf_counter() - t0) * 1000.0

            lookup_times.append(t_lookup)

            if is_hit:
                hits += 1
                if is_same:
                    correct_hits += 1
                else:
                    false_hits += 1

        hit_rate = round(hits / total, 2)
        precision = round(correct_hits / hits, 2) if hits > 0 else None
        false_hit_rate = round(false_hits / hits, 2) if hits > 0 else None
        recall_same = round(correct_hits / same_count, 2) if same_count > 0 else 0.0

        avg_lookup = round(float(np.mean(lookup_times)), 1)
        p95_lookup = round(float(np.percentile(lookup_times, 95)), 1)

        cost_per_hit = 38 * config.PRICE_IN + 34 * config.PRICE_OUT
        est_cost_saved = round(hits * cost_per_hit, 4)

        return ArenaRow(
            strategy=strat_name,
            hit_rate=hit_rate,
            precision=precision,
            false_hit_rate=false_hit_rate,
            recall_same=recall_same,
            avg_lookup_ms=avg_lookup,
            p95_lookup_ms=p95_lookup,
            llm_calls_avoided=hits,
            est_cost_saved=est_cost_saved,
        )

