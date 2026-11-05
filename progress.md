# CacheIQ Progress Log

## Builder 1 Progress

### [Phase P0] Scaffold + Contract
- **Status:** Completed
- **Created Structure:**
  - `backend/app/`: `main.py`, `routes.py`, `models.py`, `config.py`
  - `backend/engine/`: `embedding/`, `store/`, `search/`, `verifier/`, `llm/`, `strategies/`, `metrics/`, `eval/`
  - `backend/migrations/`: `001_init.sql` (exact contract from main PRD §6.1)
  - `backend/tests/fixtures/`: all 9 mock fixture files created
  - `backend/tests/`: `test_fixtures.py`, `test_mock_api.py`
  - `frontend/design/`: exported Stitch design (`cache_console.html`, `cache_console_preview.jpg`, `design_system.md`)
  - Root: `docker-compose.yml`, `.env.example`, `.env`, `Makefile`, `AGENTS.md`, `.gitignore`, `requirements.txt`
- **Contract Verification:**
  - Pydantic v2 models created for all request/response shapes in PRD §6.2
  - SQL schema frozen with pgvector HNSW index, unique active exact_key, and privacy-preserving query_log
  - `MOCK_API=1` implemented returning realistic fixtures for Builder 2 UI consumption
  - Static file mount configured to serve `frontend/`

### [Phase P1] Embeddings + In-Memory Prototype
- **Status:** Completed
- **Components Implemented:**
  - `backend/engine/embedding/embedder.py`: Singleton `sentence-transformers/all-MiniLM-L6-v2` loader, `embed()`, `embed_many()`, `cosine_similarity()`, `warm_up()`. All embeddings are L2-normalised (384-dimensional unit vectors).
  - `scripts/proto_cache.py`: In-memory prototype semantic cache with dot product lookup.
  - `backend/tests/test_embedder.py`: 5 tests verifying unit length norm (1.0), dimensionality (384), identical text (~1.0), paraphrase similarity (>0.80), and unrelated similarity (<0.40).
- **Test Suite Status:** 21 passed (all unit tests, fixture validation, and mock API endpoints).

### [Phase P2] Persistent Store
- **Status:** Completed
- **Components Implemented:**
  - `backend/engine/store/db.py`: `psycopg_pool.ConnectionPool` with automatic `register_vector` on all connections.
  - `backend/engine/store/repo.py`: Parameterised SQL queries (`insert_entry`, `get_by_exact_key`, `search_top_k` using exact SQL from PRD §4.1, `increment_hit`, `invalidate`, `list_entries`, `count`, `log_query`, `reset_all`).
  - `backend/tests/test_repo.py`: Integration test suite covering exact lookup, top-K ordering, context_key isolation, invalidation lifecycle, and unique active exact_key constraint.

### [Phase P3] Pipeline, LLM, and API
- **Status:** Completed
- **Components Implemented:**
  - `backend/engine/llm/`: `base.py` (abstract `BaseLLM`), `mock_llm.py` (deterministic with configurable simulated latency and token reporting), `gemini.py` (`google-genai` integration with 20s timeout), `factory.py`.
  - `backend/engine/search/normalizer.py`: Unicode NFKC normalization, exact_key SHA256 calculation, and config_hash generation.
  - `backend/engine/strategies/`: Strategy B (`exact_match.py`), Strategy D (`semantic_verified.py`).
  - `backend/engine/metrics/stats.py`: Live stats calculator aggregating hit rates, latencies, avoided calls, and cost savings from `query_log`.
  - `backend/app/routes.py`: Plain `def` FastAPI endpoints for `/api/health`, `/api/config`, `/api/query`, `/api/stats`, `/api/entries`, and admin reset/invalidation.
  - `backend/tests/test_pipeline.py`: 6 tests verifying exact hit, semantic hit, ambiguous band miss, below threshold miss, bypass flag, and DB error fallback.

### [Phase P4] Match Verifier
- **Status:** Completed
- **Components Implemented:**
  - `backend/engine/verifier/time_sensitive.py`: Regex-based case-insensitive detector matching all PRD §4.3 keywords (`latest`, `today`, `price`, etc.).
  - `backend/engine/verifier/verifier.py`: Pure function implementing rules V1 (expiry), V2 (config hash), V3 (embedding model), V4 (time-sensitivity), and V5 (number & year mismatch) in exact order.
  - Architectural constraint enforced: Zero imports from `engine/search` or `engine/store`.
  - `backend/tests/test_verifier.py`: 21 tests (1 AST import scanner test + 20 table-driven verification tests).

### [Phase P5] Evaluation & Cache Arena (Live PostgreSQL / pgvector)
- **Status:** Completed & Audited
- **Components Implemented:**
  - `backend/engine/eval/arena.py`: Upgraded from in-memory stand-in to `PostgresArenaRunner` executing real strategies against live PostgreSQL/pgvector. Uses per-pair context isolation (`arena:<run_id>:<pair_id>`) and parameterised SQL cleanup.
  - `scripts/threshold_sweep.py`: Live Postgres threshold sweep generating `data/results/sweep.csv` and `data/results/sweep.png`.
  - `scripts/benchmark_latency.py`: Measures full lookup path over 200 queries against 1k and 10k synthetic entries indexed by real HNSW in PostgreSQL. Saves hardware specs in `data/results/latency.json`.

### [Phase P6 & P7] Hardening, CI, & Final Numbers
- **Status:** Completed
- **Components Implemented:**
  - `lookup_ms` timing window in `semantic_verified.py`: Measures normalize + embed + search + verify per PRD §3.
  - Reliability & Determinism suite (`backend/tests/test_reliability.py`):
    - `test_llm_timeout_returns_clean_json_error_and_stores_nothing`
    - `test_llm_general_error_returns_clean_json_error_and_stores_nothing`
    - `test_arena_on_postgres_deterministic`
  - Precision handling: Zero-hit strategies (`no_cache`) output `null` ("n/a") rather than 0%.

### [Phase P8] Traffic Simulation (Zipf Workload Evaluation)
- **Status:** Completed & Audited
- **Components Implemented:**
  - `scripts/traffic_sim.py`: Deterministic traffic simulator (seed=42, N=1000 requests, Zipf exponent 1.1) on the TEST split (60 pairs, 94 intents). Evaluates strategies `no_cache`, `exact_match`, `semantic_raw`, and `semantic_verified` sequentially on live PostgreSQL with isolated context keys (`traffic:<run_id>:<strategy>:shared`) and cleanups. Tracks cumulative warm-up curve after every 50 requests.
  - `Makefile`: Added `traffic` target running `python scripts/traffic_sim.py`.
  - `backend/tests/test_traffic_sim.py`: Test suite verifying deterministic identical outputs across runs with the same seed, different outputs with varying seeds, zero query leakage outside the TEST split, zero dev-split queries, and intent variant structures (7 tests passing).
  - Saved outputs: `data/results/traffic.json` and `data/results/traffic.png` (Matplotlib cumulative hit rate vs requests).
- **Traffic Simulation Measured Results (N=1000, Zipf a=1.1, seed=42, test split):**
  - `no_cache`: Hit Rate 0.0%, Precision null ("n/a"), False Hits 0, LLM Calls Made 1000, Calls Avoided 0, Mean Lookup 0.0 ms, p95 0.0 ms, Cost Saved $0.000000, Simulated Time Saved 0.0s
  - `exact_match`: Hit Rate 88.9%, Precision 100.0%, False Hits 0, LLM Calls Made 111, Calls Avoided 889, Mean Lookup 5.7 ms, p95 8.5 ms, Cost Saved $0.023203, Simulated Time Saved 1333.5s
  - `semantic_raw`: Hit Rate 91.4%, Precision 95.84%, False Hits 38 (38 wrong answers served), LLM Calls Made 86, Calls Avoided 914, Mean Lookup 17.7 ms, p95 61.5 ms, Cost Saved $0.023855, Simulated Time Saved 1371.0s
  - `semantic_verified`: Hit Rate 88.7%, Precision 98.42%, False Hits 14 (reduced false hits by 63% vs raw), LLM Calls Made 113, Calls Avoided 887, Mean Lookup 15.0 ms, p95 52.2 ms, Cost Saved $0.023151, Simulated Time Saved 1330.5s
- **Test Suite Status:** **65 passed, 0 skipped** across entire backend test suite.

---
## Builder 2 Progress

### [Tasks B2-1 to B2-12] Complete Delivery & Verification
- **Status:** 100% Completed & Verified
- **Components Implemented:**
  - **Evaluation Dataset (`data/eval/pairs.jsonl`):** 120 human-reviewed query pairs strictly adhering to PRD §5.2.
  - **Dataset Validation Test (`backend/tests/test_dataset.py`):** Schema integrity, category distribution, non-emptiness.
  - **Modular Frontend Architecture (`frontend/js/`):** `api.js`, `chat.js`, `analytics.js`, `entries.js`, `arena.js`.
  - **Documentation & Presentation Suite:** `README.md`, `docs/demo_script.md`, `docs/dataset_notes.md`, `docs/bugs.md`, `docs/builder2.md`.
