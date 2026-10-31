"""Strategy D: Semantic Verified Caching with Match Verifier.

Pipeline stages:
1. Validate & Normalize
2. Bypass check: bypass_cache, personalized, or is_time_sensitive(norm_q) -> MISS (do NOT store)
3. Exact lookup by exact_key -> HIT_EXACT
4. Embed query (L2-normalised unit vector)
5. pgvector top-K candidate search
6. Similarity gate & Match Verifier:
   - No candidates -> MISS_NO_CANDIDATE
   - sim < T_LOW -> MISS_BELOW_THRESHOLD
   - T_LOW <= sim < T_HIT -> MISS_AMBIGUOUS
   - sim >= T_HIT -> Run Match Verifier (rules V1..V5) in rank order
     - If passes -> HIT_SEMANTIC
     - If fails -> MISS_<reason_code>
7. On MISS: call LLM, store in cache_entries (unless time-sensitive/bypass), log to query_log
8. DB failure fallback -> MISS_CACHE_ERROR (call LLM, do not store)
"""

import time
from datetime import datetime, timezone
from typing import Optional
from backend.app import config
from backend.app.models import QueryRequest, QueryResponse
from backend.engine.embedding.embedder import embed
from backend.engine.llm.factory import get_llm
from backend.engine.search.normalizer import normalize, compute_exact_key, compute_config_hash
from backend.engine.store import repo
from backend.engine.strategies.base import BaseStrategy
from backend.engine.verifier.time_sensitive import is_time_sensitive
from backend.engine.verifier.verifier import verify


class SemanticVerifiedStrategy(BaseStrategy):

    def __init__(self, t_hit: float = config.T_HIT, t_low: float = config.T_LOW):
        self.t_hit = t_hit
        self.t_low = t_low
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

        # ── Step 2: Bypass check (Time-sensitive, bypass_cache, personalized) ──
        is_ts = is_time_sensitive(norm_q)
        if req.bypass_cache or req.personalized or is_ts:
            reason = "MISS_TIME_SENSITIVE" if is_ts else "MISS_BYPASS"
            explain = (
                "Query is time-sensitive (e.g. latest, today, price); bypassing cache both ways."
                if is_ts
                else "Query bypassed cache due to request settings."
            )
            t_lookup = (time.perf_counter() - t0) * 1000.0
            llm_res = self.llm.generate(norm_q)
            t_total = (time.perf_counter() - t0) * 1000.0

            try:
                repo.log_query(
                    context_key=ctx,
                    strategy="semantic_verified",
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
                strategy="semantic_verified",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=llm_res.provider,
            )

        # ── Step 3: Exact lookup by exact_key ─────────────────────────────
        db_error = False
        exact_hit = None
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
                    strategy="semantic_verified",
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
                strategy="semantic_verified",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=config.LLM_PROVIDER,
            )

        # ── Step 4 & 5: Embed and pgvector top-K search ───────────────────
        candidates = []
        q_emb = None
        if not db_error:
            try:
                q_emb = embed(norm_q)
                candidates = repo.search_top_k(q_emb, context_key=ctx, k=5)
            except Exception:
                db_error = True

        if db_error:
            t_lookup = (time.perf_counter() - t0) * 1000.0
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
                strategy="semantic_verified",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=llm_res.provider,
            )

        # ── Step 6: Similarity gate & Match Verifier ──────────────────────
        now_utc = datetime.now(timezone.utc)
        winning_candidate = None
        best_sim = None
        outcome = "MISS"
        reason_code = "MISS_NO_CANDIDATE"
        explain = f"No cached entries found in context '{ctx}'."

        if candidates:
            best_cand = candidates[0]
            best_sim = float(best_cand["similarity"])

            if best_sim < self.t_low:
                outcome = "MISS"
                reason_code = "MISS_BELOW_THRESHOLD"
                explain = f"Best similarity {best_sim:.2f} is below lower threshold {self.t_low:.2f}."
            elif self.t_low <= best_sim < self.t_hit:
                outcome = "MISS"
                reason_code = "MISS_AMBIGUOUS"
                explain = (
                    f"Similarity {best_sim:.2f} falls into ambiguous band "
                    f"[{self.t_low:.2f}, {self.t_hit:.2f}). Preferred MISS for safety."
                )
            else:
                # Top candidate(s) >= t_hit -> Run Match Verifier in rank order
                best_failure_verdict = None
                for cand in candidates:
                    cand_sim = float(cand["similarity"])
                    if cand_sim < self.t_hit:
                        break  # Stop at threshold boundary

                    verdict = verify(
                        new_query=norm_q,
                        candidate=cand,
                        request_config_hash=self.config_hash,
                        now=now_utc,
                        current_model=config.EMBEDDING_MODEL,
                    )

                    if verdict.ok:
                        winning_candidate = cand
                        best_sim = cand_sim
                        outcome = "HIT"
                        reason_code = "HIT_SEMANTIC"
                        explain = (
                            f"Matched '{cand['query_text']}' (similarity {cand_sim:.2f} ≥ {self.t_hit:.2f}). "
                            f"{verdict.explain}"
                        )
                        break
                    else:
                        if best_failure_verdict is None:
                            best_failure_verdict = verdict

                if not winning_candidate and best_failure_verdict:
                    outcome = "MISS"
                    reason_code = best_failure_verdict.reason_code
                    explain = best_failure_verdict.explain

        # ── Step 7: Finalize HIT or MISS ──────────────────────────────────
        # Full lookup timing covers normalize + embed + search + verify (PRD §3)
        t_lookup = (time.perf_counter() - t0) * 1000.0

        if outcome == "HIT" and winning_candidate:
            try:
                repo.increment_hit(winning_candidate["id"])
                repo.log_query(
                    context_key=ctx,
                    strategy="semantic_verified",
                    outcome="HIT",
                    reason_code="HIT_SEMANTIC",
                    similarity=best_sim,
                    lookup_ms=t_lookup,
                    total_ms=t_lookup,
                    llm_called=False,
                    prompt_tokens=None,
                    completion_tokens=None,
                    matched_entry_id=winning_candidate["id"],
                )
            except Exception:
                pass

            return QueryResponse(
                answer=winning_candidate["response_text"],
                outcome="HIT",
                hit_type="SEMANTIC",
                reason_code="HIT_SEMANTIC",
                explain=explain,
                similarity=round(best_sim, 2),
                matched_query=winning_candidate["query_text"],
                matched_entry_id=winning_candidate["id"],
                llm_called=False,
                lookup_ms=round(t_lookup, 1),
                total_ms=round(t_lookup, 1),
                strategy="semantic_verified",
                embedding_model=config.EMBEDDING_MODEL,
                llm_mode=config.LLM_PROVIDER,
            )

        # Cache MISS: call LLM, store in cache, write query_log
        llm_res = self.llm.generate(norm_q)
        t_total = (time.perf_counter() - t0) * 1000.0

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
                strategy="semantic_verified",
                outcome="MISS",
                reason_code=reason_code,
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
            reason_code=reason_code,
            explain=explain,
            similarity=round(best_sim, 2) if best_sim is not None else None,
            matched_query=candidates[0]["query_text"] if candidates else None,
            matched_entry_id=None,
            llm_called=True,
            lookup_ms=round(t_lookup, 1),
            total_ms=round(t_total, 1),
            strategy="semantic_verified",
            embedding_model=config.EMBEDDING_MODEL,
            llm_mode=llm_res.provider,
        )
