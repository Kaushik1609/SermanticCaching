"""Tests for Match Verifier (backend/engine/verifier/verifier.py).

Verifies:
- Rule V1: Expiry gate (MISS_EXPIRED)
- Rule V2: Config hash mismatch (MISS_CONFIG_MISMATCH)
- Rule V3: Embedding model mismatch (MISS_CONFIG_MISMATCH)
- Rule V4: Time-sensitive keyword detection (MISS_TIME_SENSITIVE)
- Rule V5: Number & Year mismatches (MISS_NUMERIC_MISMATCH)
- Architectural boundary: Verifier MUST NOT import from engine/search or engine/store
"""

import ast
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

from backend.engine.verifier.verifier import verify, Verdict
from backend.engine.verifier.time_sensitive import is_time_sensitive, TIME_SENSITIVE_WORDS


def test_verifier_no_forbidden_imports():
    """Architectural constraint from AGENTS.md:

    engine/verifier must NOT import from engine/search or engine/store.
    """
    verifier_dir = Path(__file__).parent.parent / "engine" / "verifier"
    for py_file in verifier_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "engine.search" not in alias.name, f"Forbidden import in {py_file.name}: {alias.name}"
                    assert "engine.store" not in alias.name, f"Forbidden import in {py_file.name}: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "engine.search" not in mod, f"Forbidden import in {py_file.name}: from {mod}"
                assert "engine.store" not in mod, f"Forbidden import in {py_file.name}: from {mod}"
                assert "search" not in mod.split("."), f"Forbidden import in {py_file.name}: from {mod}"
                assert "store" not in mod.split("."), f"Forbidden import in {py_file.name}: from {mod}"


TABLE_DRIVEN_VERIFIER_CASES = [
    # ── Rule V1: Expiry cases ──
    {
        "name": "expired_candidate",
        "new_q": "What is machine learning?",
        "cand_q": "Explain machine learning.",
        "expires_at": datetime.now(timezone.utc) - timedelta(hours=2),
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_EXPIRED",
    },
    {
        "name": "unexpired_candidate_future",
        "new_q": "What is machine learning?",
        "cand_q": "Explain machine learning.",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": True,
        "expected_reason": "HIT_SEMANTIC",
    },
    {
        "name": "no_expiry_none",
        "new_q": "What is machine learning?",
        "cand_q": "Explain machine learning.",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": True,
        "expected_reason": "HIT_SEMANTIC",
    },
    # ── Rule V2: Config hash mismatch ──
    {
        "name": "config_hash_mismatch",
        "new_q": "What is machine learning?",
        "cand_q": "Explain machine learning.",
        "expires_at": None,
        "cand_config": "cfg_gemini_temp_0.7",
        "req_config": "cfg_mock_temp_0.0",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_CONFIG_MISMATCH",
    },
    # ── Rule V3: Embedding model mismatch ──
    {
        "name": "embedding_model_mismatch",
        "new_q": "What is machine learning?",
        "cand_q": "Explain machine learning.",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "bge-small-en-v1.5",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_CONFIG_MISMATCH",
    },
    # ── Rule V4: Time-sensitive keywords ──
    {
        "name": "time_sensitive_latest",
        "new_q": "What is the latest Python version?",
        "cand_q": "What is the latest Python release?",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_TIME_SENSITIVE",
    },
    {
        "name": "time_sensitive_today",
        "new_q": "What is the stock price today?",
        "cand_q": "What is the stock price today?",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_TIME_SENSITIVE",
    },
    {
        "name": "time_sensitive_price",
        "new_q": "Bitcoin price in USD",
        "cand_q": "What is Bitcoin price in USD?",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_TIME_SENSITIVE",
    },
    {
        "name": "time_sensitive_weather",
        "new_q": "What is the weather in London?",
        "cand_q": "London weather forecast",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_TIME_SENSITIVE",
    },
    {
        "name": "time_sensitive_news",
        "new_q": "AI technology news",
        "cand_q": "Latest news on AI",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_TIME_SENSITIVE",
    },
    {
        "name": "time_sensitive_right_now",
        "new_q": "Who is winning the game right now?",
        "cand_q": "Who leads the match right now?",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_TIME_SENSITIVE",
    },
    # ── Rule V5: Numeric & Year mismatch ──
    {
        "name": "numeric_mismatch_5_vs_10",
        "new_q": "Top 10 programming languages in 2024",
        "cand_q": "Top 5 programming languages in 2024",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_NUMERIC_MISMATCH",
    },
    {
        "name": "numeric_mismatch_years",
        "new_q": "Best movies of 2024",
        "cand_q": "Best movies of 2023",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_NUMERIC_MISMATCH",
    },
    {
        "name": "numeric_mismatch_counts",
        "new_q": "How to eat 3 meals a day",
        "cand_q": "How to eat 6 meals a day",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_NUMERIC_MISMATCH",
    },
    {
        "name": "numeric_mismatch_one_has_number_other_does_not",
        "new_q": "Top 5 sorting algorithms",
        "cand_q": "Top sorting algorithms",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": False,
        "expected_reason": "MISS_NUMERIC_MISMATCH",
    },
    {
        "name": "numeric_match_same_numbers",
        "new_q": "Top 10 frameworks in 2024",
        "cand_q": "10 best frameworks in 2024",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": True,
        "expected_reason": "HIT_SEMANTIC",
    },
    # ── Paraphrase passes completely ──
    {
        "name": "paraphrase_no_numbers_passes",
        "new_q": "What is machine learning in simple terms?",
        "cand_q": "Can you explain machine learning simply?",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": True,
        "expected_reason": "HIT_SEMANTIC",
    },
    {
        "name": "paraphrase_capital_of_france",
        "new_q": "Tell me the capital city of France.",
        "cand_q": "What is the capital of France?",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": True,
        "expected_reason": "HIT_SEMANTIC",
    },
    {
        "name": "paraphrase_backpropagation",
        "new_q": "How does backpropagation work in neural networks?",
        "cand_q": "Explain backpropagation algorithm.",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": True,
        "expected_reason": "HIT_SEMANTIC",
    },
    {
        "name": "paraphrase_reverse_linked_list",
        "new_q": "How to reverse a linked list in Python?",
        "cand_q": "Reverse linked list Python implementation",
        "expires_at": None,
        "cand_config": "cfg_same",
        "req_config": "cfg_same",
        "cand_model": "all-MiniLM-L6-v2",
        "cur_model": "all-MiniLM-L6-v2",
        "expected_ok": True,
        "expected_reason": "HIT_SEMANTIC",
    },
]


@pytest.mark.parametrize("case", TABLE_DRIVEN_VERIFIER_CASES, ids=lambda c: c["name"])
def test_match_verifier_table_driven(case):
    now = datetime.now(timezone.utc)
    candidate = {
        "query_text": case["cand_q"],
        "expires_at": case["expires_at"],
        "config_hash": case["cand_config"],
        "embedding_model": case["cand_model"],
    }

    verdict = verify(
        new_query=case["new_q"],
        candidate=candidate,
        request_config_hash=case["req_config"],
        now=now,
        current_model=case["cur_model"],
    )

    assert verdict.ok == case["expected_ok"], f"Failed on {case['name']}: {verdict.explain}"
    assert verdict.reason_code == case["expected_reason"], f"Wrong reason for {case['name']}: got {verdict.reason_code}"

