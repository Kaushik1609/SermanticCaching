"""Strategy B: Exact Match Caching.

Performs exact key lookup only. Serves as traditional caching baseline in Cache Arena.
"""

import time
from backend.app import config
from backend.app.models import QueryRequest, QueryResponse
from backend.engine.embedding.embedder import embed
from backend.engine.llm.factory import get_llm
from backend.engine.search.normalizer import normalize, compute_exact_key, compute_config_hash
from backend.engine.store import repo
from backend.engine.strategies.base import BaseStrategy


class ExactMatchStrategy(BaseStrategy):

    def __init__(self):
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

        # Bypass check
        if req.bypass_cache or req.personalized:
            t_lookup = (time.perf_counter() - t0) * 1000.0
            llm_res = self.llm.generate(norm_q)
            t_total = (time.perf_counter() - t0) * 1000.0

            try:
                repo.log_query(
                    context_key=ctx,
                    strategy="exact_match",
                    outcome="MISS",
                    reason_code="MISS_BYPASS",
                    similarity=None,
                    lookup_ms=t_lookup,
                    total_ms=t_total,
                    llm_called=True,
                    prompt_tokens=llm_res.prompt_tokens,
                    completion_tokens=llm_res.completion_tokens,
                )
            except Exception:
                pass

            return QueryResponse(
                answer=llm_res.text,
                outcome="MISS",
                hit_type=None,
                reason_code="MISS_BYPASS",
                explain="Query bypassed cache due to request settings.",
                similarity=None,
                matched_query=None,
                matched_entry_id=None,
                llm_called=True,
                lookup_ms=round(t_lookup, 1),
                total_ms=round(t_total, 1),
                strategy="exact_match",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=llm_res.provider,
            )

        # Exact DB lookup
        db_error = False
        cached_entry = None
        try:
            cached_entry = repo.get_by_exact_key(exact_key, context_key=ctx)
        except Exception:
            db_error = True

        t_lookup = (time.perf_counter() - t0) * 1000.0

        if cached_entry:
            try:
                repo.increment_hit(cached_entry["id"])
                repo.log_query(
                    context_key=ctx,
                    strategy="exact_match",
                    outcome="HIT",
                    reason_code="HIT_EXACT",
                    similarity=1.0,
                    lookup_ms=t_lookup,
                    total_ms=t_lookup,
                    llm_called=False,
                    prompt_tokens=None,
                    completion_tokens=None,
                    matched_entry_id=cached_entry["id"],
                )
            except Exception:
                pass

            return QueryResponse(
                answer=cached_entry["response_text"],
                outcome="HIT",
                hit_type="EXACT",
                reason_code="HIT_EXACT",
                explain="Exact match found for this query, context, and config.",
                similarity=1.0,
                matched_query=cached_entry["query_text"],
                matched_entry_id=cached_entry["id"],
                llm_called=False,
                lookup_ms=round(t_lookup, 1),
                total_ms=round(t_lookup, 1),
                strategy="exact_match",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=config.LLM_PROVIDER,
            )

        # Cache MISS -> Call LLM
        llm_res = self.llm.generate(norm_q)
        t_total = (time.perf_counter() - t0) * 1000.0

        # Store in DB if DB is healthy
        reason = "MISS_CACHE_ERROR" if db_error else "MISS_NO_CANDIDATE"
        explain = (
            "Database error during lookup. Served directly from LLM."
            if db_error
            else "No exact match found in cache."
        )

        if not db_error:
            try:
                emb = embed(norm_q)
                repo.insert_entry(
                    context_key=ctx,
                    query_text=norm_q,
                    exact_key=exact_key,
                    query_embedding=emb,
                    response_text=llm_res.text,
                    embedding_model=config.EMBEDDING_MODEL,
                    config_hash=self.config_hash,
                    prompt_tokens=llm_res.prompt_tokens,
                    completion_tokens=llm_res.completion_tokens,
                )
                repo.log_query(
                    context_key=ctx,
                    strategy="exact_match",
                    outcome="MISS",
                    reason_code=reason,
                    similarity=None,
                    lookup_ms=t_lookup,
                    total_ms=t_total,
                    llm_called=True,
                    prompt_tokens=llm_res.prompt_tokens,
                    completion_tokens=llm_res.completion_tokens,
                )
            except Exception:
                pass

        return QueryResponse(
            answer=llm_res.text,
            outcome="MISS",
            hit_type=None,
            reason_code=reason,
            explain=explain,
            similarity=None,
            matched_query=None,
            matched_entry_id=None,
            llm_called=True,
            lookup_ms=round(t_lookup, 1),
            total_ms=round(t_total, 1),
            strategy="exact_match",
            embedding_model=config.EMBEDDING_MODEL,
            llm_mode=llm_res.provider,
        )

