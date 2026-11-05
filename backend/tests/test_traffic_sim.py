"""Tests for traffic_sim.py — determinism and split enforcement."""

import json
from pathlib import Path

import pytest

# We import the building blocks, not the full runner (which needs Postgres).
from scripts.traffic_sim import (
    load_pairs,
    filter_test_split,
    build_intents,
    build_query_to_intent,
    generate_workload,
    SEED,
    N_REQUESTS,
    ZIPF_EXPONENT,
    DATA_FILE,
)


@pytest.fixture(scope="module")
def test_pairs():
    """Load test-split pairs once."""
    all_pairs = load_pairs(DATA_FILE)
    return filter_test_split(all_pairs)


@pytest.fixture(scope="module")
def dev_pairs():
    """Load dev-split pairs once."""
    all_pairs = load_pairs(DATA_FILE)
    has_split = any("split" in p for p in all_pairs)
    if has_split:
        return [p for p in all_pairs if p.get("split") == "dev"]
    # Deterministic fallback: first half per category = dev
    from collections import defaultdict
    by_cat = defaultdict(list)
    for p in all_pairs:
        by_cat[p["category"]].append(p)
    dev = []
    for cat in sorted(by_cat.keys()):
        cat_pairs = sorted(by_cat[cat], key=lambda p: p["id"])
        mid = len(cat_pairs) // 2
        dev.extend(cat_pairs[:mid])
    return sorted(dev, key=lambda p: p["id"])


@pytest.fixture(scope="module")
def intents(test_pairs):
    return build_intents(test_pairs)


@pytest.fixture(scope="module")
def query_to_intent(intents):
    return build_query_to_intent(intents)


class TestDeterminism:
    """Two runs with the same seed must produce identical workloads."""

    def test_two_runs_identical(self, intents):
        """Generate workload twice with seed=42; assert identical output."""
        w1 = generate_workload(intents, n=N_REQUESTS, exponent=ZIPF_EXPONENT, seed=SEED)
        w2 = generate_workload(intents, n=N_REQUESTS, exponent=ZIPF_EXPONENT, seed=SEED)
        assert len(w1) == len(w2) == N_REQUESTS
        for i in range(N_REQUESTS):
            assert w1[i] == w2[i], f"Mismatch at index {i}: {w1[i]} != {w2[i]}"

    def test_different_seed_differs(self, intents):
        """Different seed produces a different workload."""
        w1 = generate_workload(intents, n=100, exponent=ZIPF_EXPONENT, seed=42)
        w2 = generate_workload(intents, n=100, exponent=ZIPF_EXPONENT, seed=99)
        # At least some elements should differ
        diffs = sum(1 for a, b in zip(w1, w2) if a != b)
        assert diffs > 0, "Different seeds should produce different workloads"


class TestSplitEnforcement:
    """No request in the workload may use a query outside the test split."""

    def test_no_variant_outside_test_split(self, test_pairs, intents):
        """All workload queries must come from the test split."""
        # Collect all test-split queries
        test_queries = set()
        for p in test_pairs:
            test_queries.add(p["query_a"])
            test_queries.add(p["query_b"])

        workload = generate_workload(intents, n=N_REQUESTS, exponent=ZIPF_EXPONENT, seed=SEED)
        workload_queries = set(q for q, _ in workload)

        outside = workload_queries - test_queries
        assert len(outside) == 0, (
            f"Found {len(outside)} queries outside test split: {outside}"
        )

    def test_no_dev_queries_in_workload(self, test_pairs, dev_pairs, intents):
        """Verify workload does not contain any dev-only queries."""
        test_queries = set()
        for p in test_pairs:
            test_queries.add(p["query_a"])
            test_queries.add(p["query_b"])

        dev_only_queries = set()
        for p in dev_pairs:
            dev_only_queries.add(p["query_a"])
            dev_only_queries.add(p["query_b"])
        dev_only_queries -= test_queries  # remove overlap

        workload = generate_workload(intents, n=N_REQUESTS, exponent=ZIPF_EXPONENT, seed=SEED)
        workload_queries = set(q for q, _ in workload)

        leaked = workload_queries & dev_only_queries
        assert len(leaked) == 0, (
            f"Found {len(leaked)} dev-only queries in workload: {leaked}"
        )


class TestIntentBuilding:
    """Verify intent structure."""

    def test_same_pairs_have_two_variants(self, test_pairs, intents, query_to_intent):
        """Each 'same' pair should produce an intent with 2 variants."""
        same_pairs = [p for p in test_pairs if p["label"] == "same"]
        for p in same_pairs:
            qa_intent = query_to_intent.get(p["query_a"])
            qb_intent = query_to_intent.get(p["query_b"])
            assert qa_intent is not None, f"query_a not in intent map: {p['query_a']}"
            assert qb_intent is not None, f"query_b not in intent map: {p['query_b']}"
            assert qa_intent == qb_intent, (
                f"Pair {p['id']}: query_a and query_b should share an intent"
            )

    def test_different_pair_queries_are_separate_intents(self, test_pairs, query_to_intent):
        """Queries from 'different' pairs should be in separate intents."""
        diff_pairs = [p for p in test_pairs if p["label"] == "different"]
        for p in diff_pairs:
            qa_intent = query_to_intent.get(p["query_a"])
            qb_intent = query_to_intent.get(p["query_b"])
            # They should exist and be different
            if qa_intent is not None and qb_intent is not None:
                assert qa_intent != qb_intent, (
                    f"Pair {p['id']}: different-labelled queries should NOT "
                    f"share an intent"
                )

    def test_zipf_distribution_skewed(self, intents):
        """Zipf distribution should be skewed — top intent gets more traffic."""
        workload = generate_workload(intents, n=N_REQUESTS, exponent=ZIPF_EXPONENT, seed=SEED)
        from collections import Counter
        counts = Counter(intent_idx for _, intent_idx in workload)
        top_count = counts.most_common(1)[0][1]
        # Top intent should have at least 3% of traffic with 1.1 exponent
        assert top_count >= N_REQUESTS * 0.03, (
            f"Top intent only has {top_count} hits, expected Zipf skew"
        )

