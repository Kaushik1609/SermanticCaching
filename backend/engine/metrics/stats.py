"""Live Metrics & Cost Calculation from query_log.

Source of truth: PRD §5.3 and §6.2.
"""

from typing import Dict, Any
from backend.app import config
from backend.app.models import StatsResponse
from backend.engine.store.db import get_db


def get_live_stats() -> StatsResponse:
    """Compute live telemetry aggregated across all query_log rows."""
    stats_query = """
        SELECT
            COUNT(*) AS total_queries,
            COUNT(*) FILTER (WHERE outcome = 'HIT') AS hits,
            COUNT(*) FILTER (WHERE outcome = 'MISS') AS misses,
            AVG(lookup_ms) AS avg_lookup_ms,
            AVG(total_ms) FILTER (WHERE outcome = 'HIT') AS avg_total_ms_hit,
            AVG(total_ms) FILTER (WHERE outcome = 'MISS') AS avg_total_ms_miss,
            COUNT(*) FILTER (WHERE llm_called = true) AS llm_calls_made,
            COUNT(*) FILTER (WHERE outcome = 'HIT') AS llm_calls_avoided
        FROM query_log;
    """

    reasons_query = """
        SELECT reason_code, COUNT(*) AS cnt
        FROM query_log
        GROUP BY reason_code;
    """

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(stats_query)
            row = cur.fetchone() or {}

            cur.execute(reasons_query)
            reason_rows = cur.fetchall() or []

    total_queries = int(row.get("total_queries") or 0)
    hits = int(row.get("hits") or 0)
    misses = int(row.get("misses") or 0)
    hit_rate = round(hits / total_queries, 2) if total_queries > 0 else 0.0

    avg_lookup_ms = round(float(row.get("avg_lookup_ms") or 0.0), 1)
    avg_total_ms_hit = round(float(row.get("avg_total_ms_hit") or 0.0), 1)
    avg_total_ms_miss = round(float(row.get("avg_total_ms_miss") or 0.0), 1)

    llm_calls_made = int(row.get("llm_calls_made") or 0)
    llm_calls_avoided = int(row.get("llm_calls_avoided") or 0)

    by_reason: Dict[str, int] = {r["reason_code"]: int(r["cnt"]) for r in reason_rows}

    # Cost calculation formula: PRD §5.3
    # saved = sum over HITs of (prompt_tokens * price_in + completion_tokens * price_out)
    assumed_prompt_tokens = 38
    assumed_completion_tokens = 34
    cost_per_hit = (
        assumed_prompt_tokens * config.PRICE_IN + assumed_completion_tokens * config.PRICE_OUT
    )
    est_cost_saved = round(hits * cost_per_hit, 4)
    cost_assumptions = (
        f"assumed {assumed_prompt_tokens} prompt, {assumed_completion_tokens} completion tokens; "
        f"price_in={config.PRICE_IN}, price_out={config.PRICE_OUT}"
    )

    return StatsResponse(
        total_queries=total_queries,
        hits=hits,
        misses=misses,
        hit_rate=hit_rate,
        avg_lookup_ms=avg_lookup_ms,
        avg_total_ms_hit=avg_total_ms_hit,
        avg_total_ms_miss=avg_total_ms_miss,
        llm_calls_made=llm_calls_made,
        llm_calls_avoided=llm_calls_avoided,
        est_cost_saved=est_cost_saved,
        cost_assumptions=cost_assumptions,
        by_reason=by_reason,
    )

