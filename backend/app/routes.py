"""CacheIQ Real API routes (Plain def endpoints per AGENTS.md)."""

import time
from collections import defaultdict
from fastapi import APIRouter, Header, HTTPException, Request
import psycopg

from backend.app.models import (
    QueryRequest,
    QueryResponse,
    StatsResponse,
    EntriesResponse,
    EntryItem,
    HealthResponse,
    ConfigResponse,
    ArenaResponse,
)
from backend.app import config
from backend.engine.embedding import embedder
from backend.engine.eval.arena import run_arena, get_latest_arena
from backend.engine.metrics.stats import get_live_stats
from backend.engine.strategies.no_cache import NoCacheStrategy
from backend.engine.strategies.exact_match import ExactMatchStrategy
from backend.engine.strategies.semantic_raw import SemanticRawStrategy
from backend.engine.strategies.semantic_verified import SemanticVerifiedStrategy
from backend.engine.store import repo

router = APIRouter(prefix="/api")

# Strategy singletons
_no_cache_strategy = NoCacheStrategy()
_exact_strategy = ExactMatchStrategy()
_raw_strategy = SemanticRawStrategy()
_semantic_strategy = SemanticVerifiedStrategy()

# Per-IP rate limiting: sliding window (max 60 requests per 60 seconds)
_rate_limit_records = defaultdict(list)
_RATE_LIMIT_MAX_REQUESTS = 60
_RATE_LIMIT_WINDOW_SECONDS = 60.0


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    history = _rate_limit_records[client_ip]
    # Prune timestamps older than window
    valid = [ts for ts in history if now - ts < _RATE_LIMIT_WINDOW_SECONDS]
    _rate_limit_records[client_ip] = valid
    if len(valid) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 60 requests per minute."
        )
    _rate_limit_records[client_ip].append(now)


def _check_db() -> bool:
    """Check if Postgres DB is accessible."""
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=1) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
def health():
    """Liveness check: database status, model loaded, llm_mode."""
    db_ok = _check_db()
    model_loaded = embedder._model is not None
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_ok=db_ok,
        model_loaded=model_loaded,
        llm_mode=config.LLM_PROVIDER,
        version="2.0.0",
    )


@router.get("/config", response_model=ConfigResponse)
def get_config():
    """Read-only system configuration."""
    return ConfigResponse(
        t_hit=config.T_HIT,
        t_low=config.T_LOW,
        embedding_model=config.EMBEDDING_MODEL,
        llm_mode=config.LLM_PROVIDER,
        price_in=config.PRICE_IN,
        price_out=config.PRICE_OUT,
    )


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request):
    """Primary CacheIQ query pipeline endpoint."""
    # Per-IP rate limit check
    client_ip = request.client.host if request.client else "127.0.0.1"
    _check_rate_limit(client_ip)

    # Validation per PRD §4.1: non-empty, <= 2000 chars
    q = req.query.strip() if req.query else ""
    if not q or len(q) > 2000:
        raise HTTPException(status_code=422, detail="Query must be between 1 and 2000 characters.")

    # Select strategy
    strat_name = (req.strategy or "semantic_verified").lower()
    try:
        if strat_name == "exact_match":
            return _exact_strategy.handle(req)
        elif strat_name == "semantic_raw":
            return _raw_strategy.handle(req)
        elif strat_name == "no_cache":
            return _no_cache_strategy.handle(req)
        else:
            # Default strategy D: semantic_verified
            return _semantic_strategy.handle(req)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM backend error: {str(exc)}")


@router.get("/stats", response_model=StatsResponse)
def stats():
    """Aggregated live telemetry and cost savings."""
    try:
        return get_live_stats()
    except Exception as e:
        # If DB not available, return zeroed stats
        return StatsResponse(
            total_queries=0,
            hits=0,
            misses=0,
            hit_rate=0.0,
            avg_lookup_ms=0.0,
            avg_total_ms_hit=0.0,
            avg_total_ms_miss=0.0,
            llm_calls_made=0,
            llm_calls_avoided=0,
            est_cost_saved=0.0,
            cost_assumptions="Database offline; live stats unavailable.",
            by_reason={},
        )


@router.get("/entries", response_model=EntriesResponse)
def entries(limit: int = 50, offset: int = 0):
    """List cache entries with pagination."""
    try:
        items, total = repo.list_entries(limit=limit, offset=offset)
        return EntriesResponse(
            items=[EntryItem(**item) for item in items],
            total=total,
        )
    except Exception:
        return EntriesResponse(items=[], total=0)


@router.post("/entries/{entry_id}/invalidate")
def invalidate_entry(entry_id: int, x_admin_key: str = Header(None)):
    """Mark an entry as INVALIDATED."""
    if x_admin_key != config.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    try:
        success = repo.invalidate(entry_id)
        return {"status": "invalidated" if success else "not_found", "id": entry_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/reset")
def admin_reset(x_admin_key: str = Header(None)):
    """Clear all cache entries and query logs for a fresh demo."""
    if x_admin_key != config.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    try:
        repo.reset_all()
        return {"status": "reset", "message": "Cache and query logs cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/arena/run", response_model=ArenaResponse)
def arena_run():
    """Execute evaluation benchmark across strategies A, B, C, D."""
    return run_arena()


@router.get("/arena/latest", response_model=ArenaResponse)
def arena_latest():
    """Retrieve the most recent arena benchmark evaluation result."""
    return get_latest_arena()

