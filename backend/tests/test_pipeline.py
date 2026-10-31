"""Unit tests for Strategy D (SemanticVerifiedStrategy) and Strategy B (ExactMatchStrategy).

Tests decision pipeline logic:
- Same query twice -> HIT_EXACT and LLM not called
- Paraphrase candidate >= T_HIT -> HIT_SEMANTIC
- Ambiguous band [T_LOW, T_HIT) -> MISS_AMBIGUOUS
- Below threshold < T_LOW -> MISS_BELOW_THRESHOLD
- Bypass cache flag -> MISS_BYPASS
- DB failure -> MISS_CACHE_ERROR fallback to LLM
"""

from unittest.mock import patch
import pytest

from backend.app.models import QueryRequest
from backend.engine.strategies.exact_match import ExactMatchStrategy
from backend.engine.strategies.semantic_verified import SemanticVerifiedStrategy


@pytest.fixture
def exact_strategy():
    return ExactMatchStrategy()


@pytest.fixture
def semantic_strategy():
    # Use standard T_HIT=0.85, T_LOW=0.75
    return SemanticVerifiedStrategy(t_hit=0.85, t_low=0.75)


def test_exact_strategy_hit(exact_strategy):
    """Exact match strategy returns HIT_EXACT when entry exists in cache."""
    mock_entry = {
        "id": 42,
        "query_text": "what is machine learning?",
        "response_text": "Machine learning learns patterns.",
    }

    with patch("backend.engine.store.repo.get_by_exact_key", return_value=mock_entry), \
         patch("backend.engine.store.repo.increment_hit") as mock_inc, \
         patch("backend.engine.store.repo.log_query") as mock_log:

        req = QueryRequest(query="What is machine learning?")
        res = exact_strategy.handle(req)

        assert res.outcome == "HIT"
        assert res.hit_type == "EXACT"
        assert res.reason_code == "HIT_EXACT"
        assert res.similarity == 1.0
        assert res.llm_called is False
        assert res.answer == "Machine learning learns patterns."
        mock_inc.assert_called_once_with(42)
        mock_log.assert_called_once()


def test_semantic_strategy_hit_paraphrase(semantic_strategy):
    """Candidate with similarity >= T_HIT returns HIT_SEMANTIC without calling LLM."""
    mock_candidate = {
        "id": 12,
        "query_text": "What is machine learning?",
        "response_text": "Machine learning is learning patterns from data.",
        "similarity": 0.91,
    }

    with patch("backend.engine.store.repo.get_by_exact_key", return_value=None), \
         patch("backend.engine.store.repo.search_top_k", return_value=[mock_candidate]), \
         patch("backend.engine.store.repo.increment_hit") as mock_inc, \
         patch("backend.engine.store.repo.log_query") as mock_log:

        req = QueryRequest(query="Explain machine learning simply.")
        res = semantic_strategy.handle(req)

        assert res.outcome == "HIT"
        assert res.hit_type == "SEMANTIC"
        assert res.reason_code == "HIT_SEMANTIC"
        assert res.similarity == 0.91
        assert res.llm_called is False
        assert "0.91" in res.explain
        mock_inc.assert_called_once_with(12)


def test_semantic_strategy_ambiguous_band_miss(semantic_strategy):
    """Candidate with similarity in [T_LOW, T_HIT) returns MISS_AMBIGUOUS."""
    mock_candidate = {
        "id": 99,
        "query_text": "What is deep learning?",
        "response_text": "Deep learning uses deep neural networks.",
        "similarity": 0.79,  # In [0.75, 0.85)
    }

    with patch("backend.engine.store.repo.get_by_exact_key", return_value=None), \
         patch("backend.engine.store.repo.search_top_k", return_value=[mock_candidate]), \
         patch("backend.engine.store.repo.insert_entry") as mock_insert, \
         patch("backend.engine.store.repo.log_query") as mock_log:

        req = QueryRequest(query="What is machine learning?")
        res = semantic_strategy.handle(req)

        assert res.outcome == "MISS"
        assert res.hit_type is None
        assert res.reason_code == "MISS_AMBIGUOUS"
        assert res.similarity == 0.79
        assert res.llm_called is True
        assert "ambiguous band" in res.explain
        mock_insert.assert_called_once()


def test_semantic_strategy_below_threshold_miss(semantic_strategy):
    """Candidate with similarity < T_LOW returns MISS_BELOW_THRESHOLD."""
    mock_candidate = {
        "id": 5,
        "query_text": "How to make pizza dough?",
        "response_text": "Mix flour, water, yeast, salt.",
        "similarity": 0.42,
    }

    with patch("backend.engine.store.repo.get_by_exact_key", return_value=None), \
         patch("backend.engine.store.repo.search_top_k", return_value=[mock_candidate]), \
         patch("backend.engine.store.repo.insert_entry") as mock_insert, \
         patch("backend.engine.store.repo.log_query"):

        req = QueryRequest(query="What is machine learning?")
        res = semantic_strategy.handle(req)

        assert res.outcome == "MISS"
        assert res.reason_code == "MISS_BELOW_THRESHOLD"
        assert res.similarity == 0.42
        assert res.llm_called is True
        mock_insert.assert_called_once()


def test_bypass_cache_flag(semantic_strategy):
    """When bypass_cache is True, cache is not checked and entry is not stored."""
    with patch("backend.engine.store.repo.get_by_exact_key") as mock_exact, \
         patch("backend.engine.store.repo.search_top_k") as mock_search, \
         patch("backend.engine.store.repo.insert_entry") as mock_insert, \
         patch("backend.engine.store.repo.log_query"):

        req = QueryRequest(query="What is Python?", bypass_cache=True)
        res = semantic_strategy.handle(req)

        assert res.outcome == "MISS"
        assert res.reason_code == "MISS_BYPASS"
        assert res.llm_called is True
        mock_exact.assert_not_called()
        mock_search.assert_not_called()
        mock_insert.assert_not_called()


def test_db_failure_fallback_to_llm(semantic_strategy):
    """If DB raises an error during lookup, fall back to LLM with MISS_CACHE_ERROR."""
    with patch("backend.engine.store.repo.get_by_exact_key", side_effect=Exception("DB connection refused")), \
         patch("backend.engine.store.repo.insert_entry") as mock_insert:

        req = QueryRequest(query="What is machine learning?")
        res = semantic_strategy.handle(req)

        assert res.outcome == "MISS"
        assert res.reason_code == "MISS_CACHE_ERROR"
        assert res.llm_called is True
        assert "[mock answer]" in res.answer
        mock_insert.assert_not_called()

