"""Strategy A: No Cache (Direct LLM Baseline).

Always forwards requests to the LLM backend. Used in Cache Arena as performance and cost baseline.
"""

import time
from backend.app import config
from backend.app.models import QueryRequest, QueryResponse
from backend.engine.llm.factory import get_llm
from backend.engine.search.normalizer import normalize
from backend.engine.strategies.base import BaseStrategy


class NoCacheStrategy(BaseStrategy):

    def __init__(self, llm=None):
        self.llm = llm or get_llm()

    def handle(self, req: QueryRequest) -> QueryResponse:
        t0 = time.perf_counter()
        norm_q = normalize(req.query)

        # Direct LLM invocation without any cache lookup
        t_lookup = 0.0
        llm_res = self.llm.generate(norm_q)
        t_total = (time.perf_counter() - t0) * 1000.0

        return QueryResponse(
            answer=llm_res.text,
            outcome="MISS",
            hit_type=None,
            reason_code="MISS_NO_CACHE",
            explain="Strategy 'no_cache' always queries the LLM directly.",
            similarity=None,
            matched_query=None,
            matched_entry_id=None,
            llm_called=True,
            lookup_ms=round(t_lookup, 1),
            total_ms=round(t_total, 1),
            strategy="no_cache",
            embedding_model=config.EMBEDDING_MODEL,
            llm_mode=llm_res.provider,
        )

