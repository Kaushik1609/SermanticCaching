"""Strategy C: Semantic Raw (Bare Vector Threshold Baseline).

Pipeline:
1. Exact key lookup
2. Top-1 semantic candidate search
3. If top-1 similarity >= T_HIT: HIT_SEMANTIC
4. NO Match Verifier (no V1..V5 checks)
5. NO ambiguous band

Purpose in Cache Arena: Demonstrates why bare vector thresholding produces false hits
on numeric, time-sensitive, and config-mismatched queries.
"""

import time
from backend.app import config
from backend.app.models import QueryRequest, QueryResponse
from backend.engine.embedding.embedder import embed
from backend.engine.llm.factory import get_llm
from backend.engine.search.normalizer import normalize, compute_exact_key, compute_config_hash
from backend.engine.store import repo
from backend.engine.strategies.base import BaseStrategy


class SemanticRawStrategy(BaseStrategy):

    def __init__(self, t_hit: float = config.T_HIT):
        self.t_hit = t_hit
        self.llm = get_llm()
        self.config_hash = compute_config_hash(
            provider=config.LLM_PROVIDER,
            model="default",
            temperature=0.0,
        )

    def handle(self, req: QueryRequest) -> QueryResponse:
        t0 = time.perf_counter()
        norm_q = normalize(req.query)
        ctx = req.context_key or "default"
        exact_key = compute_exact_key(norm_q, ctx, self.config_hash)

        # 1. Exact lookup
        exact_hit = None
        db_error = False
        try:
            exact_hit = repo.get_by_exact_key(exact_key, context_key=ctx)
        except Exception:
            db_error = True

        if exact_hit:
            t_lookup = (time.perf_counter() - t0) * 1000.0
            try:
                repo.increment_hit(exact_hit["id"])
                repo.log_query(
                    context_key=ctx,
                    strategy="semantic_raw",
                    outcome="HIT",
                    reason_code="HIT_EXACT",
                    similarity=1.0,
                    lookup_ms=t_lookup,
                    total_ms=t_lookup,
                    llm_called=False,
                    prompt_tokens=None,
                    completion_tokens=None,
                    matched_entry_id=exact_hit["id"],
                )
            except Exception:
                pass

            return QueryResponse(
                answer=exact_hit["response_text"],
                outcome="HIT",
                hit_type="EXACT",
                reason_code="HIT_EXACT",
                explain=f"Exact match found for query in context '{ctx}'.",
                similarity=1.0,
                matched_query=exact_hit["query_text"],
                matched_entry_id=exact_hit["id"],
                llm_called=False,
                lookup_ms=round(t_lookup, 1),
                total_ms=round(t_lookup, 1),
                strategy="semantic_raw",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=config.LLM_PROVIDER,
            )

        # 2. Top-1 semantic lookup
        candidates = []
        q_emb = None
        if not db_error:
            try:
                q_emb = embed(norm_q)
                candidates = repo.search_top_k(q_emb, context_key=ctx, k=1)
            except Exception:
                db_error = True

        t_lookup = (time.perf_counter() - t0) * 1000.0

        if db_error:
            llm_res = self.llm.generate(norm_q)
            t_total = (time.perf_counter() - t0) * 1000.0
            return QueryResponse(
                answer=llm_res.text,
                outcome="MISS",
                hit_type=None,
                reason_code="MISS_CACHE_ERROR",
                explain="Database/search error. Served directly from LLM without caching.",
                similarity=None,
                matched_query=None,
                matched_entry_id=None,
                llm_called=True,
                lookup_ms=round(t_lookup, 1),
                total_ms=round(t_total, 1),
                strategy="semantic_raw",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=llm_res.provider,
            )

        # Bare threshold decision (no verifier, no ambiguous band)
        if candidates and float(candidates[0]["similarity"]) >= self.t_hit:
            cand = candidates[0]
            sim = float(cand["similarity"])
            try:
                repo.increment_hit(cand["id"])
                repo.log_query(
                    context_key=ctx,
                    strategy="semantic_raw",
                    outcome="HIT",
                    reason_code="HIT_SEMANTIC",
                    similarity=sim,
                    lookup_ms=t_lookup,
                    total_ms=t_lookup,
                    llm_called=False,
                    prompt_tokens=None,
                    completion_tokens=None,
                    matched_entry_id=cand["id"],
                )
            except Exception:
                pass

            return QueryResponse(
                answer=cand["response_text"],
                outcome="HIT",
                hit_type="SEMANTIC",
                reason_code="HIT_SEMANTIC",
                explain=f"Matched '{cand['query_text']}' with raw similarity {sim:.2f} >= {self.t_hit:.2f}.",
                similarity=round(sim, 2),
                matched_query=cand["query_text"],
                matched_entry_id=cand["id"],
                llm_called=False,
                lookup_ms=round(t_lookup, 1),
                total_ms=round(t_lookup, 1),
                strategy="semantic_raw",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=config.LLM_PROVIDER,
            )

        # MISS
        llm_res = self.llm.generate(norm_q)
        t_total = (time.perf_counter() - t0) * 1000.0
        best_sim = float(candidates[0]["similarity"]) if candidates else None
        reason = "MISS_BELOW_THRESHOLD" if candidates else "MISS_NO_CANDIDATE"

        try:
            if q_emb is None:
                q_emb = embed(norm_q)
            repo.insert_entry(
                context_key=ctx,
                query_text=norm_q,
                exact_key=exact_key,
                query_embedding=q_emb,
                response_text=llm_res.text,
                embedding_model=config.EMBEDDING_MODEL,
                config_hash=self.config_hash,
                prompt_tokens=llm_res.prompt_tokens,
                completion_tokens=llm_res.completion_tokens,
            )
            repo.log_query(
                context_key=ctx,
                strategy="semantic_raw",
                outcome="MISS",
                reason_code=reason,
                similarity=best_sim,
                lookup_ms=t_lookup,
                total_ms=t_total,
                llm_called=True,
                prompt_tokens=llm_res.prompt_tokens,
                completion_tokens=llm_res.completion_tokens,
                matched_entry_id=None,
            )
        except Exception:
            pass

        return QueryResponse(
            answer=llm_res.text,
            outcome="MISS",
            hit_type=None,
            reason_code=reason,
            explain=f"No match >= {self.t_hit:.2f}.",
            similarity=round(best_sim, 2) if best_sim is not None else None,
            matched_query=candidates[0]["query_text"] if candidates else None,
            matched_entry_id=None,
            llm_called=True,
            lookup_ms=round(t_lookup, 1),
            total_ms=round(t_total, 1),
            strategy="semantic_raw",
            embedding_model=config.EMBEDDING_MODEL,
            llm_mode=llm_res.provider,
        )

