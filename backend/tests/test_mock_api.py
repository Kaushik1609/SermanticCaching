"""Tests for the Mock API server mode (MOCK_API=1)."""

import os
import pytest
from fastapi.testclient import TestClient

# Ensure MOCK_API=1 before loading app
os.environ["MOCK_API"] = "1"
from backend.app.main import app

client = TestClient(app)


def test_mock_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["db_ok"] is True


def test_mock_config():
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert data["t_hit"] == 0.85
    assert data["embedding_model"] == "all-MiniLM-L6-v2"


def test_mock_query():
    payload = {
        "query": "Can you define machine learning?",
        "context_key": "default",
        "strategy": "semantic_verified",
        "bypass_cache": False,
        "personalized": False,
    }
    res = client.post("/api/query", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["outcome"] == "HIT"
    assert data["reason_code"] == "HIT_SEMANTIC"


def test_mock_stats():
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_queries"] == 120
    assert data["hits"] == 54


def test_mock_entries():
    res = client.get("/api/entries")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] == 31


def test_mock_arena():
    res = client.get("/api/arena/latest")
    assert res.status_code == 200
    data = res.json()
    assert data["run_id"] == "r42"


def test_static_files_root():
    res = client.get("/")
    assert res.status_code == 200
    assert "CacheIQ" in res.text

