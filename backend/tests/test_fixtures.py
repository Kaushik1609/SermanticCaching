"""Tests verifying that mock fixtures strictly conform to Pydantic models."""

import json
from pathlib import Path
import pytest
from backend.app.models import (
    QueryResponse,
    StatsResponse,
    EntriesResponse,
    ArenaResponse,
    HealthResponse,
    ConfigResponse,
    ErrorResponse,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str):
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def test_fixture_query_hit_semantic():
    data = load_fixture("query_hit_semantic.json")
    obj = QueryResponse.model_validate(data)
    assert obj.outcome == "HIT"
    assert obj.hit_type == "SEMANTIC"
    assert obj.reason_code == "HIT_SEMANTIC"
    assert obj.similarity == 0.91
    assert obj.matched_entry_id == 12


def test_fixture_query_hit_exact():
    data = load_fixture("query_hit_exact.json")
    obj = QueryResponse.model_validate(data)
    assert obj.outcome == "HIT"
    assert obj.hit_type == "EXACT"
    assert obj.reason_code == "HIT_EXACT"
    assert obj.similarity == 1.0


def test_fixture_query_miss():
    data = load_fixture("query_miss.json")
    obj = QueryResponse.model_validate(data)
    assert obj.outcome == "MISS"
    assert obj.hit_type is None
    assert obj.similarity is None
    assert obj.llm_called is True


def test_fixture_stats():
    data = load_fixture("stats.json")
    obj = StatsResponse.model_validate(data)
    assert obj.total_queries == 120
    assert obj.hits == 54
    assert obj.misses == 66
    assert obj.hit_rate == 0.45
    assert "HIT_SEMANTIC" in obj.by_reason


def test_fixture_entries():
    data = load_fixture("entries.json")
    obj = EntriesResponse.model_validate(data)
    assert len(obj.items) == 2
    assert obj.total == 31
    assert obj.items[0].id == 12


def test_fixture_arena():
    data = load_fixture("arena.json")
    obj = ArenaResponse.model_validate(data)
    assert obj.run_id == "r42"
    assert len(obj.rows) == 4
    assert obj.winner.precision == "semantic_verified"


def test_fixture_health():
    data = load_fixture("health.json")
    obj = HealthResponse.model_validate(data)
    assert obj.status == "ok"
    assert obj.db_ok is True
    assert obj.model_loaded is True


def test_fixture_config():
    data = load_fixture("config.json")
    obj = ConfigResponse.model_validate(data)
    assert obj.t_hit == 0.85
    assert obj.t_low == 0.75
    assert obj.embedding_model == "all-MiniLM-L6-v2"


def test_fixture_error_validation():
    data = load_fixture("error_validation.json")
    obj = ErrorResponse.model_validate(data)
    assert obj.error.code == "VALIDATION_ERROR"

