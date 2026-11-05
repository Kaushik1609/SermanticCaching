"""CacheIQ Traffic Simulator — Zipf-distributed workload from the TEST split.

Builds "intents" from pairs.jsonl (TEST split only):
  - Pairs labelled "same" form one intent with two variants (query_a, query_b).
  - Every query that appears in a "different" pair is its own single-variant intent.
Draws N=1000 requests using Zipf popularity (exponent 1.1, seed 42).

Runs the stream through all 4 strategies using REAL strategies, repo, and
Postgres/pgvector, each in its own isolated context_key (cleaned up afterwards).
Mock LLM at latency_ms=0 for timing.

Ground truth: a HIT is correct only if the matched entry's query belongs to the
same intent as the request; otherwise it is a false hit.

Saves:
  data/results/traffic.json   — per-strategy metrics + warm-up curves
  data/results/traffic.png    — cumulative hit rate vs requests chart

Source of truth: docs/00_MAIN_PRD.md §4, §5, §6.
"""

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from backend.app import config
from backend.app.models import QueryRequest, QueryResponse
from backend.engine.llm.mock_llm import MockLLM
from backend.engine.store import repo
from backend.engine.strategies.no_cache import NoCacheStrategy
from backend.engine.strategies.exact_match import ExactMatchStrategy
from backend.engine.strategies.semantic_raw import SemanticRawStrategy
from backend.engine.strategies.semantic_verified import SemanticVerifiedStrategy

# ── Paths ────────────────────────────────────────────────────────────────
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "eval" / "pairs.jsonl"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "data" / "results"
RESULTS_JSON = RESULTS_DIR / "traffic.json"
RESULTS_PNG = RESULTS_DIR / "traffic.png"

# ── Constants ────────────────────────────────────────────────────────────
SEED = 42
N_REQUESTS = 1000
ZIPF_EXPONENT = 1.1
WARMUP_INTERVAL = 50

# Cost assumptions from engine/metrics/stats.py (PRD §5.3)
ASSUMED_PROMPT_TOKENS = 38
ASSUMED_COMPLETION_TOKENS = 34


# ── Data loading ─────────────────────────────────────────────────────────

def load_pairs(filepath: Path = DATA_FILE) -> List[Dict[str, Any]]:
    """Load all pairs from pairs.jsonl."""
    pairs = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def filter_test_split(pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only pairs belonging to the test split.

    If pairs have an explicit 'split' field, use it.
    Otherwise use deterministic stratified assignment:
    sort pairs by (category, id), first half per category = dev, second = test.
    """
    # Check if any pair has an explicit split field
    has_split = any("split" in p for p in pairs)
    if has_split:
        return [p for p in pairs if p.get("split") == "test"]

    # Deterministic stratified assignment
    from collections import defaultdict
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in pairs:
        by_cat[p["category"]].append(p)

    test_pairs = []
    for cat in sorted(by_cat.keys()):
        cat_pairs = sorted(by_cat[cat], key=lambda p: p["id"])
        mid = len(cat_pairs) // 2
        test_pairs.extend(cat_pairs[mid:])  # second half = test

    return sorted(test_pairs, key=lambda p: p["id"])


# ── Intent building ──────────────────────────────────────────────────────

def build_intents(pairs: List[Dict[str, Any]]) -> List[List[str]]:
    """Build intents from pairs.

    - "same" pairs form one intent with two variants (query_a, query_b).
    - Every query in a "different" pair is its own single-variant intent.

    Returns a list of intents, where each intent is a list of query strings.
    """
    intents: List[List[str]] = []
    different_queries: Set[str] = set()

    for p in pairs:
        if p["label"] == "same":
            variants = [p["query_a"]]
            if p["query_b"] != p["query_a"]:
                variants.append(p["query_b"])
            else:
                # exact dup — still two variants but with same text
                variants.append(p["query_b"])
            intents.append(variants)
        else:
            # Each query in a "different" pair is its own intent
            different_queries.add(p["query_a"])
            different_queries.add(p["query_b"])

    # Deduplicate queries that appear in "same" pairs
    same_queries: Set[str] = set()
    for intent in intents:
        for q in intent:
            same_queries.add(q)

    # Add remaining "different" queries as single-variant intents
    for q in sorted(different_queries):
        if q not in same_queries:
            intents.append([q])

    return intents


def build_query_to_intent(intents: List[List[str]]) -> Dict[str, int]:
    """Map every query variant to its intent index."""
    mapping: Dict[str, int] = {}
    for idx, variants in enumerate(intents):
        for q in variants:
            mapping[q] = idx
    return mapping


# ── Workload generation ──────────────────────────────────────────────────

def generate_workload(
    intents: List[List[str]],
    n: int = N_REQUESTS,
    exponent: float = ZIPF_EXPONENT,
    seed: int = SEED,
) -> List[Tuple[str, int]]:
    """Generate N requests with Zipf popularity distribution.

    Returns list of (query_text, intent_index) tuples.
    """
    rng = np.random.default_rng(seed)
    n_intents = len(intents)

    # Zipf weights: rank k has weight 1/k^s
    ranks = np.arange(1, n_intents + 1, dtype=np.float64)
    weights = 1.0 / np.power(ranks, exponent)
    weights /= weights.sum()

    # Draw intent indices according to Zipf
    intent_indices = rng.choice(n_intents, size=n, p=weights)

    # For each draw, pick a random variant within the intent
    workload: List[Tuple[str, int]] = []
    for intent_idx in intent_indices:
        variants = intents[intent_idx]
        variant_idx = rng.integers(0, len(variants))
        workload.append((variants[variant_idx], int(intent_idx)))

    return workload


# ── Strategy runner ──────────────────────────────────────────────────────

def run_strategy(
    strat_name: str,
    workload: List[Tuple[str, int]],
    query_to_intent: Dict[str, int],
    run_id: str,
) -> Dict[str, Any]:
    """Run a full workload through one strategy, collecting detailed metrics.

    Ground truth: a HIT is correct only if the matched entry's query
    belongs to the same intent as the request.
    """
    mock_llm = MockLLM(simulated_latency_ms=0)
    ctx_prefix = f"traffic:{run_id}:{strat_name}"

    if strat_name == "no_cache":
        strat = NoCacheStrategy(llm=mock_llm)
    elif strat_name == "exact_match":
        strat = ExactMatchStrategy(llm=mock_llm)
    elif strat_name == "semantic_raw":
        strat = SemanticRawStrategy(t_hit=config.T_HIT, llm=mock_llm)
    elif strat_name == "semantic_verified":
        strat = SemanticVerifiedStrategy(
            t_hit=config.T_HIT, t_low=config.T_LOW, llm=mock_llm
        )
    else:
        raise ValueError(f"Unknown strategy: {strat_name}")

    hits = 0
    correct_hits = 0
    false_hits = 0
    llm_calls = 0
    lookup_times: List[float] = []
    cumulative_hit_rate: List[Dict[str, Any]] = []

    try:
        for i, (query, expected_intent) in enumerate(workload):
            ctx = f"{ctx_prefix}:shared"
            req = QueryRequest(query=query, context_key=ctx)
            resp = strat.handle(req)

            lookup_times.append(resp.lookup_ms)

            if resp.llm_called:
                llm_calls += 1

            if resp.outcome == "HIT":
                hits += 1
                # Ground truth: check if matched query belongs to same intent
                matched_q = resp.matched_query
                if matched_q and matched_q in query_to_intent:
                    if query_to_intent[matched_q] == expected_intent:
                        correct_hits += 1
                    else:
                        false_hits += 1
                else:
                    # matched_query not in our intent map — could be a
                    # normalized variant; check if it is semantically the same
                    # For exact matches the stored text IS the normalized form
                    # of a query in the same intent, so check all variants
                    from backend.engine.search.normalizer import normalize
                    norm_matched = normalize(matched_q) if matched_q else None
                    found = False
                    if norm_matched:
                        for q_variant in query_to_intent:
                            if normalize(q_variant) == norm_matched:
                                if query_to_intent[q_variant] == expected_intent:
                                    correct_hits += 1
                                    found = True
                                    break
                    if not found and matched_q:
                        false_hits += 1

            # Record warm-up curve every WARMUP_INTERVAL requests
            if (i + 1) % WARMUP_INTERVAL == 0:
                cumulative_hit_rate.append({
                    "requests": i + 1,
                    "hit_rate": round(hits / (i + 1), 4),
                })
    finally:
        try:
            repo.cleanup_context_prefix(f"{ctx_prefix}:")
        except Exception:
            pass

    total = len(workload)
    hit_rate = round(hits / total, 4) if total > 0 else 0.0
    precision = round(correct_hits / hits, 4) if hits > 0 else None
    llm_avoided = hits
    llm_made = llm_calls

    # Latency stats
    lookup_arr = np.array(lookup_times) if lookup_times else np.array([0.0])
    mean_lookup = round(float(np.mean(lookup_arr)), 2)
    p95_lookup = round(float(np.percentile(lookup_arr, 95)), 2)

    # Cost saved (assumed) — PRD §5.3
    cost_per_hit = (
        ASSUMED_PROMPT_TOKENS * config.PRICE_IN
        + ASSUMED_COMPLETION_TOKENS * config.PRICE_OUT
    )
    est_cost_saved = round(hits * cost_per_hit, 6)

    # Simulated LLM time saved (label "simulated")
    simulated_llm_ms = config.MOCK_LLM_LATENCY_MS  # default 1500 ms
    simulated_time_saved_ms = hits * simulated_llm_ms

    return {
        "strategy": strat_name,
        "total_requests": total,
        "hits": hits,
        "correct_hits": correct_hits,
        "false_hits": false_hits,
        "hit_rate": hit_rate,
        "precision": precision,
        "llm_calls_made": llm_made,
        "llm_calls_avoided": llm_avoided,
        "mean_lookup_ms": mean_lookup,
        "p95_lookup_ms": p95_lookup,
        "est_cost_saved_assumed": est_cost_saved,
        "simulated_llm_time_saved_ms": simulated_time_saved_ms,
        "cumulative_hit_rate": cumulative_hit_rate,
    }


# ── Chart ────────────────────────────────────────────────────────────────

def plot_warmup_curves(results: List[Dict[str, Any]], output: Path) -> None:
    """Plot cumulative hit rate vs requests, one line per strategy."""
    fig, ax = plt.subplots(figsize=(10, 6))

    colors = {
        "no_cache": "#9CA3AF",
        "exact_match": "#3B82F6",
        "semantic_raw": "#F59E0B",
        "semantic_verified": "#10B981",
    }
    labels = {
        "no_cache": "A: No Cache",
        "exact_match": "B: Exact Match",
        "semantic_raw": "C: Semantic Raw",
        "semantic_verified": "D: Semantic Verified",
    }

    for r in results:
        strat = r["strategy"]
        curve = r["cumulative_hit_rate"]
        if not curve:
            continue
        xs = [pt["requests"] for pt in curve]
        ys = [pt["hit_rate"] * 100 for pt in curve]
        ax.plot(
            xs, ys,
            marker="o", markersize=3,
            color=colors.get(strat, "#6B7280"),
            label=labels.get(strat, strat),
            linewidth=2,
        )

    ax.set_xlabel("Requests", fontsize=12)
    ax.set_ylabel("Cumulative Hit Rate (%)", fontsize=12)
    ax.set_title(
        f"CacheIQ Traffic Simulation - Cache Warm-Up Curve\n"
        f"(N={N_REQUESTS}, Zipf a={ZIPF_EXPONENT}, seed={SEED}, TEST split)",
        fontsize=13,
    )
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, N_REQUESTS + 50)
    ax.set_ylim(bottom=0)

    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)


# ── Table printer ────────────────────────────────────────────────────────

def print_table(results: List[Dict[str, Any]]) -> None:
    """Print a compact summary table to stdout."""
    header = (
        f"{'Strategy':<20} {'Hit%':>6} {'Prec':>6} {'FalseH':>6} "
        f"{'LLM Made':>8} {'Avoided':>7} {'Mean ms':>7} {'p95 ms':>7} "
        f"{'Cost$ (assumed)':>15} {'Time Saved (simulated)':>22}"
    )
    print("\n" + "=" * len(header))
    print("CacheIQ Traffic Simulation Results")
    print(f"N={N_REQUESTS}  Zipf a={ZIPF_EXPONENT}  seed={SEED}  split=test")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for r in results:
        prec_str = f"{r['precision']:.2%}" if r["precision"] is not None else "n/a"
        time_saved = f"{r['simulated_llm_time_saved_ms'] / 1000:.1f}s"
        print(
            f"{r['strategy']:<20} {r['hit_rate']:>5.1%} {prec_str:>6} "
            f"{r['false_hits']:>6} {r['llm_calls_made']:>8} "
            f"{r['llm_calls_avoided']:>7} {r['mean_lookup_ms']:>7.1f} "
            f"{r['p95_lookup_ms']:>7.1f} "
            f"${r['est_cost_saved_assumed']:>13.6f} "
            f"{time_saved:>22}"
        )

    print("=" * len(header))
    print("Cost labels: 'assumed' (fixed token counts from config)")
    print("Time labels: 'simulated' (mock LLM latency × hits)")
    print()


# ── Main ─────────────────────────────────────────────────────────────────

def run_traffic_sim(
    seed: int = SEED,
    n: int = N_REQUESTS,
) -> Dict[str, Any]:
    """Run the full traffic simulation and return the results dict."""
    print(f"Loading pairs from {DATA_FILE} ...")
    all_pairs = load_pairs(DATA_FILE)
    test_pairs = filter_test_split(all_pairs)
    print(f"  Total pairs: {len(all_pairs)}, test split: {len(test_pairs)}")

    intents = build_intents(test_pairs)
    query_to_intent = build_query_to_intent(intents)
    print(f"  Intents: {len(intents)} ({sum(1 for i in intents if len(i) > 1)} multi-variant)")

    # Collect all valid queries for the test to verify
    all_test_queries = set()
    for p in test_pairs:
        all_test_queries.add(p["query_a"])
        all_test_queries.add(p["query_b"])

    print(f"\nGenerating workload: N={n}, Zipf a={ZIPF_EXPONENT}, seed={seed} ...")
    workload = generate_workload(intents, n=n, exponent=ZIPF_EXPONENT, seed=seed)

    # Verify all queries are from test split
    workload_queries = set(q for q, _ in workload)
    assert workload_queries.issubset(all_test_queries), (
        f"Workload contains queries outside test split: "
        f"{workload_queries - all_test_queries}"
    )

    run_id = f"tsim_{uuid.uuid4().hex[:8]}"
    strategies = ["no_cache", "exact_match", "semantic_raw", "semantic_verified"]
    results: List[Dict[str, Any]] = []

    for strat_name in strategies:
        print(f"\n  Running {strat_name} ({n} requests) ...", flush=True)
        t0 = time.perf_counter()
        result = run_strategy(strat_name, workload, query_to_intent, run_id)
        elapsed = time.perf_counter() - t0
        print(f"    Done in {elapsed:.1f}s - hits={result['hits']}, "
              f"false_hits={result['false_hits']}, precision={result['precision']}", flush=True)
        results.append(result)

    # Print table
    print_table(results)

    # Save JSON
    output = {
        "seed": seed,
        "n_requests": n,
        "zipf_exponent": ZIPF_EXPONENT,
        "split": "test",
        "n_test_pairs": len(test_pairs),
        "n_intents": len(intents),
        "n_multi_variant_intents": sum(1 for i in intents if len(i) > 1),
        "t_hit": config.T_HIT,
        "t_low": config.T_LOW,
        "strategies": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Results saved to {RESULTS_JSON}")

    # Plot
    plot_warmup_curves(results, RESULTS_PNG)
    print(f"Chart saved to {RESULTS_PNG}")

    return output


if __name__ == "__main__":
    run_traffic_sim()
