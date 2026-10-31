"""CacheIQ Cache Arena Evaluator (PostgreSQL / pgvector live runner).

Runs all 4 strategies (no_cache, exact_match, semantic_raw, semantic_verified)
on the labelled evaluation dataset (data/eval/pairs.jsonl) using real Postgres/pgvector.

Protocol from PRD §5.2:
- Context isolation per pair: arena:<run_id>:<pair_id>
- Send query_a (stores answer), then query_b (probes cache)
- Real strategies, real repo, real pgvector (<=> distance)
- Mock LLM mode (latency set to 0 for benchmark efficiency)
- Parameterized SQL cleanup of arena rows after execution
- Saves output to data/results/arena.json
"""

import json
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

from backend.app import config
from backend.app.models import (
    QueryRequest,
    ArenaRow,
    ArenaWinner,
    ArenaResponse,
)
from backend.engine.llm.mock_llm import MockLLM
from backend.engine.store import repo
from backend.engine.strategies.base import BaseStrategy
from backend.engine.strategies.no_cache import NoCacheStrategy
from backend.engine.strategies.exact_match import ExactMatchStrategy
from backend.engine.strategies.semantic_raw import SemanticRawStrategy
from backend.engine.strategies.semantic_verified import SemanticVerifiedStrategy


DATA_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "eval" / "pairs.jsonl"
RESULTS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "results" / "arena.json"


def load_dataset() -> List[Dict[str, Any]]:
    """Load pairs from pairs.jsonl."""
    if not DATA_FILE.exists():
        return []
    pairs = []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


class PostgresArenaRunner:
    """Evaluates CacheIQ strategies against live PostgreSQL/pgvector store."""

    def __init__(self, t_hit: float = config.T_HIT, t_low: float = config.T_LOW):
        self.t_hit = t_hit
        self.t_low = t_low
        self.mock_llm = MockLLM(latency_ms=0)

    def _get_strategy(self, strat_name: str) -> BaseStrategy:
        if strat_name == "no_cache":
            strat = NoCacheStrategy(llm=self.mock_llm)
        elif strat_name == "exact_match":
            strat = ExactMatchStrategy(llm=self.mock_llm)
        elif strat_name == "semantic_raw":
            strat = SemanticRawStrategy(t_hit=self.t_hit, llm=self.mock_llm)
        elif strat_name == "semantic_verified":
            strat = SemanticVerifiedStrategy(t_hit=self.t_hit, t_low=self.t_low, llm=self.mock_llm)
        else:
            raise ValueError(f"Unknown strategy: {strat_name}")

        return strat
        return strat

    def evaluate_strategy(
        self,
        strat_name: str,
        pairs: List[Dict[str, Any]],
        run_id: Optional[str] = None,
    ) -> ArenaRow:
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

        if not run_id:
            run_id = f"r_{uuid.uuid4().hex[:6]}"

        strat = self._get_strategy(strat_name)
        hits = 0
        correct_hits = 0
        false_hits = 0
        same_count = sum(1 for p in pairs if p.get("label") == "same")
        lookup_times: List[float] = []

        try:
            for idx, p in enumerate(pairs):
                pair_id = p.get("id", f"P{idx:03d}")
                ctx = f"arena:{run_id}:{pair_id}"
                q_a = p["query_a"]
                q_b = p["query_b"]
                is_same = (p.get("label") == "same")

                # Ingest query_a (stores cached entry in isolated context)
                req_a = QueryRequest(query=q_a, context_key=ctx)
                strat.handle(req_a)

                # Probe query_b (evaluates cache behavior)
                req_b = QueryRequest(query=q_b, context_key=ctx)
                resp_b = strat.handle(req_b)

                lookup_times.append(resp_b.lookup_ms)

                if resp_b.outcome == "HIT":
                    hits += 1
                    if is_same:
                        correct_hits += 1
                    else:
                        false_hits += 1
        finally:
            # Clean up all rows inserted for this arena run in PostgreSQL
            try:
                repo.cleanup_context_prefix(f"arena:{run_id}:")
            except Exception:
                pass

        hit_rate = round(hits / total, 2)
        # PRD requirement: precision is null ("n/a") for strategies with zero hits, not 0%
        precision = round(correct_hits / hits, 2) if hits > 0 else None
        false_hit_rate = round(false_hits / hits, 2) if hits > 0 else None
        recall_same = round(correct_hits / same_count, 2) if same_count > 0 else 0.0

        avg_lookup = round(float(np.mean(lookup_times)), 1) if lookup_times else 0.0
        p95_lookup = round(float(np.percentile(lookup_times, 95)), 1) if lookup_times else 0.0

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


# Backward-compatible alias
InProcessArenaRunner = PostgresArenaRunner
ArenaRunner = PostgresArenaRunner


def run_arena(t_hit: float = config.T_HIT, t_low: float = config.T_LOW, run_id: Optional[str] = None) -> ArenaResponse:
    """Execute evaluation across strategies A, B, C, D on pairs.jsonl using live Postgres."""
    pairs = load_dataset()
    runner = PostgresArenaRunner(t_hit=t_hit, t_low=t_low)

    if not run_id:
        run_id = f"r_{uuid.uuid4().hex[:6]}"

    strategies = ["no_cache", "exact_match", "semantic_raw", "semantic_verified"]
    rows: List[ArenaRow] = []

    for strat in strategies:
        row = runner.evaluate_strategy(strat, pairs, run_id=run_id)
        rows.append(row)

    # Determine winners (precision winner chosen only among strategies with hits)
    valid_prec_rows = [r for r in rows if r.precision is not None]
    if valid_prec_rows:
        winner_precision = max(valid_prec_rows, key=lambda r: (r.precision, -(r.false_hit_rate or 0.0))).strategy
    else:
        winner_precision = "semantic_verified"

    winner_hit_rate = max(rows, key=lambda r: r.hit_rate).strategy

    res = ArenaResponse(
        run_id=run_id,
        dataset_size=len(pairs),
        thresholds={"T_HIT": t_hit, "T_LOW": t_low},
        llm_mode="mock",
        rows=rows,
        winner=ArenaWinner(precision=winner_precision, hit_rate=winner_hit_rate),
    )

    # Save to data/results/arena.json
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(res.model_dump(), f, indent=2)

    return res


def get_latest_arena() -> Optional[ArenaResponse]:
    """Load latest arena result from file or run if missing."""
    if not RESULTS_FILE.exists():
        return run_arena()
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ArenaResponse(**data)
