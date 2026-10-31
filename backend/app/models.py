"""CacheIQ — Pydantic v2 models (frozen contract)."""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Request models ──────────────────────────────────────────────

class QueryRequest(BaseModel):
    """POST /api/query request body."""
    query: str = Field(..., min_length=1, max_length=2000)
    context_key: str = Field(default="default")
    strategy: str = Field(default="semantic_verified")
    bypass_cache: bool = Field(default=False)
    personalized: bool = Field(default=False)


# ── Response models ─────────────────────────────────────────────

class QueryResponse(BaseModel):
    """POST /api/query response."""
    answer: str
    outcome: str              # HIT | MISS
    hit_type: Optional[str] = None   # EXACT | SEMANTIC | None
    reason_code: str
    explain: str
    similarity: Optional[float] = None
    matched_query: Optional[str] = None
    matched_entry_id: Optional[int] = None
    llm_called: bool
    lookup_ms: float
    total_ms: float
    strategy: str
    embedding_model: str
    llm_mode: str             # mock | gemini | ollama


class StatsResponse(BaseModel):
    """GET /api/stats response."""
    total_queries: int
    hits: int
    misses: int
    hit_rate: float
    avg_lookup_ms: float
    avg_total_ms_hit: float
    avg_total_ms_miss: float
    llm_calls_made: int
    llm_calls_avoided: int
    est_cost_saved: float
    cost_assumptions: str
    by_reason: dict[str, int]


class EntryItem(BaseModel):
    """Single entry in GET /api/entries response."""
    id: int
    query_text: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    hit_count: int
    status: str
    context_key: str


class EntriesResponse(BaseModel):
    """GET /api/entries response."""
    items: list[EntryItem]
    total: int


class ArenaRow(BaseModel):
    """One strategy row in the arena result."""
    strategy: str
    hit_rate: float
    precision: Optional[float] = None
    false_hit_rate: Optional[float] = None
    recall_same: float
    avg_lookup_ms: float
    p95_lookup_ms: float
    llm_calls_avoided: int
    est_cost_saved: float


class ArenaWinner(BaseModel):
    """Winner by each metric."""
    precision: str
    hit_rate: str


class ArenaResponse(BaseModel):
    """POST /api/arena/run and GET /api/arena/latest response."""
    run_id: str
    dataset_size: int
    thresholds: dict[str, float]
    llm_mode: str
    rows: list[ArenaRow]
    winner: ArenaWinner


class HealthResponse(BaseModel):
    """GET /api/health response."""
    status: str
    db_ok: bool
    model_loaded: bool
    llm_mode: str
    version: str = "2.0.0"


class ConfigResponse(BaseModel):
    """GET /api/config response."""
    t_hit: float
    t_low: float
    embedding_model: str
    llm_mode: str
    price_in: float
    price_out: float


class ErrorDetail(BaseModel):
    """Error shape."""
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Error wrapper."""
    error: ErrorDetail
