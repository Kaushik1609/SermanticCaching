"""CacheIQ — FastAPI application entry point."""

import os
import json
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app import config
from backend.engine.embedding import embedder


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up embedding model at startup so first user request is not delayed
    try:
        embedder.warm_up()
    except Exception:
        pass
    yield


app = FastAPI(title="CacheIQ", version="2.0.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code = "VALIDATION_ERROR" if exc.status_code == 422 else "ERROR"
    if exc.status_code in (502, 504):
        code = "LLM_ERROR"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": str(exc)}},
    )

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


# Check environment dynamically for mock mode
is_mock = os.getenv("MOCK_API", "0") == "1" or config.MOCK_API

if is_mock:
    @app.get("/api/health")
    def mock_health():
        return _load_fixture("health.json")

    @app.get("/api/config")
    def mock_config():
        return _load_fixture("config.json")

    @app.post("/api/query")
    def mock_query(request: Request):
        return _load_fixture("query_hit_semantic.json")

    @app.get("/api/stats")
    def mock_stats():
        return _load_fixture("stats.json")

    @app.get("/api/entries")
    def mock_entries():
        return _load_fixture("entries.json")

    @app.post("/api/entries/{entry_id}/invalidate")
    def mock_invalidate(entry_id: int):
        return {"status": "invalidated", "id": entry_id}

    @app.post("/api/admin/reset")
    def mock_reset():
        return {"status": "reset", "message": "Cache and logs cleared."}

    @app.post("/api/arena/run")
    def mock_arena_run():
        return _load_fixture("arena.json")

    @app.get("/api/arena/latest")
    def mock_arena_latest():
        return _load_fixture("arena.json")

else:
    from backend.app.routes import router
    app.include_router(router)


# ── Static file serving ─────────────────────────────────────────
# Mounted AFTER all API routes so /api/* routes take precedence
frontend_dir = Path(__file__).parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
