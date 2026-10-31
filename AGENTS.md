Project: CacheIQ — explainable semantic cache for LLM apps. Source of truth: docs/00_MAIN_PRD.md.
Rules:
- Python 3.11, FastAPI, Pydantic v2, psycopg 3 + pgvector. Endpoints are plain `def` (not async).
- Never change models.py, migrations/001_init.sql or the API shapes without updating docs/00_MAIN_PRD.md first.
- engine/verifier must NOT import from engine/search or engine/store.
- Embeddings are L2-normalised. similarity = 1 - cosine_distance (pgvector `<=>`).
- Parameterised SQL only. No secrets in code. No query text in logs.
- Every module gets unit tests. `pytest` must pass before any commit.
- No Redis, RAG, encryption, or extra frameworks. Docker is for Postgres only.
- Update progress.md after each step; update activeContext.md when a decision changes.
