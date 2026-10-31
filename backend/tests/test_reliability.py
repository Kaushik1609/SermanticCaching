"""Tests for Reliability & Determinism (Phase P5 audit fixes).

Verifies:
1. LLM timeout or error returns a clean JSON error {"error": {"code": ..., "message": ...}}
   and stores nothing in the cache.
2. Arena evaluation running against live PostgreSQL/pgvector is deterministic across two runs.
"""

from unittest.mock import patch, MagicMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from backend.app.main import http_exception_handler, validation_exception_handler
from backend.app.routes import router, _semantic_strategy
from backend.app import config
from backend.engine.eval.arena import load_dataset, PostgresArenaRunner
from backend.engine.store import repo


@pytest.fixture
def test_client():
    test_app = FastAPI()
    test_app.add_exception_handler(HTTPException, http_exception_handler)
    test_app.add_exception_handler(RequestValidationError, validation_exception_handler)
    test_app.include_router(router)
    return TestClient(test_app)


def test_llm_timeout_returns_clean_json_error_and_stores_nothing(test_client):
    """When LLM times out or errors, endpoint returns clean JSON error and stores nothing."""
    timeout_err = TimeoutError("Request timed out connecting to Gemini LLM provider after 10000ms")

    with patch("backend.engine.strategies.semantic_verified.repo.get_by_exact_key", return_value=None), \
         patch("backend.engine.strategies.semantic_verified.repo.search_top_k", return_value=[]), \
         patch("backend.engine.strategies.semantic_verified.repo.insert_entry") as mock_insert, \
         patch.object(_semantic_strategy.llm, "generate", side_effect=timeout_err):

        res = test_client.post("/api/query", json={"query": "Explain quantum cryptography algorithms."})

        # Must return clean HTTP error
        assert res.status_code == 502
        data = res.json()

        # Must conform to PRD §7 error format: {"error": {"code": ..., "message": ...}}
        assert "error" in data
        assert data["error"]["code"] == "LLM_ERROR"
        assert "timed out" in data["error"]["message"].lower()

        # Crucial requirement: stores nothing in cache on failure
        mock_insert.assert_not_called()


def test_llm_general_error_returns_clean_json_error_and_stores_nothing(test_client):
    """When LLM throws generic runtime error, returns clean JSON error and stores nothing."""
    runtime_err = RuntimeError("Upstream API quota exceeded or service unavailable")

    with patch("backend.engine.strategies.semantic_verified.repo.get_by_exact_key", return_value=None), \
         patch("backend.engine.strategies.semantic_verified.repo.search_top_k", return_value=[]), \
         patch("backend.engine.strategies.semantic_verified.repo.insert_entry") as mock_insert, \
         patch.object(_semantic_strategy.llm, "generate", side_effect=runtime_err):

        res = test_client.post("/api/query", json={"query": "Explain database indexing in PostgreSQL."})

        assert res.status_code == 502
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "LLM_ERROR"
        assert "quota exceeded" in data["error"]["message"].lower()

        mock_insert.assert_not_called()


def test_arena_on_postgres_deterministic():
    """Running arena on Postgres across two runs yields identical metrics."""
    pairs = load_dataset()
    assert len(pairs) > 0, "pairs.jsonl must contain evaluation pairs"

    runner1 = PostgresArenaRunner(t_hit=config.T_HIT, t_low=config.T_LOW)
    row1 = runner1.evaluate_strategy("semantic_verified", pairs, run_id="det_run_1")

    runner2 = PostgresArenaRunner(t_hit=config.T_HIT, t_low=config.T_LOW)
    row2 = runner2.evaluate_strategy("semantic_verified", pairs, run_id="det_run_2")

    # Metrics across two runs must match exactly
    assert row1.hit_rate == row2.hit_rate
    assert row1.precision == row2.precision
    assert row1.false_hit_rate == row2.false_hit_rate
    assert row1.recall_same == row2.recall_same
    assert row1.llm_calls_avoided == row2.llm_calls_avoided
    assert row1.est_cost_saved == row2.est_cost_saved

