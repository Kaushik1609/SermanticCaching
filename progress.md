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
- **Prototype Benchmark Output:**
```
================================================================================
CacheIQ In-Memory Semantic Cache Prototype (Model: sentence-transformers/all-MiniLM-L6-v2)
Similarity Threshold T_HIT = 0.85
================================================================================
#   | Stored Query / Probe Query                           | Sim    | Status | Expected
--------------------------------------------------------------------------------
1   | Stored: What is machine learning?
    | Probe:  Explain machine learning.
    | Sim: 0.8269  Result: MISS  Expected: HIT   Cat: paraphrase        [FAIL]
--------------------------------------------------------------------------------
2   | Stored: How does backpropagation work?
    | Probe:  Explain backpropagation in neural networks.
    | Sim: 0.8822  Result: HIT   Expected: HIT   Cat: paraphrase        [OK]
--------------------------------------------------------------------------------
3   | Stored: What is the capital of France?
    | Probe:  Tell me the capital city of France.
    | Sim: 0.9177  Result: HIT   Expected: HIT   Cat: paraphrase        [OK]
--------------------------------------------------------------------------------
4   | Stored: How to reverse a linked list in Python?
    | Probe:  Reverse linked list Python code
    | Sim: 0.9429  Result: HIT   Expected: HIT   Cat: paraphrase        [OK]
--------------------------------------------------------------------------------
5   | Stored: What is Python?
    | Probe:  What is the latest Python version?
    | Sim: 0.6177  Result: MISS  Expected: MISS  Cat: related_different [OK]
--------------------------------------------------------------------------------
6   | Stored: Top 5 programming languages in 2024
    | Probe:  Top 10 programming languages in 2024
    | Sim: 0.9788  Result: HIT   Expected: MISS  Cat: numeric           [FAIL]
--------------------------------------------------------------------------------
7   | Stored: What is the capital of France?
    | Probe:  What is the capital of Germany?
    | Sim: 0.6632  Result: MISS  Expected: MISS  Cat: related_different [OK]
--------------------------------------------------------------------------------
8   | Stored: How to sort a list in Python?
    | Probe:  How to reverse a linked list in Python?
    | Sim: 0.4779  Result: MISS  Expected: MISS  Cat: related_different [OK]
--------------------------------------------------------------------------------
```
*Key insight from benchmark:* Pair 6 ("Top 5" vs "Top 10") exhibits 0.9788 cosine similarity, proving why a bare vector threshold causes dangerous false hits and motivating the Match Verifier (rule V5) in Phase P4. Pair 1 falls into the ambiguous band [0.75, 0.85).

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
  - `backend/engine/eval/arena.py`: Upgraded from in-memory stand-in to `PostgresArenaRunner` executing real strategies against live PostgreSQL/pgvector. Uses per-pair context isolation (`arena:<run_id>:<pair_id>`) and parameterised SQL cleanup. Reference in-memory runner preserved under `backend/tests/in_memory_arena.py`.
  - `scripts/threshold_sweep.py`: Live Postgres threshold sweep generating `data/results/sweep.csv` and `data/results/sweep.png`.
  - `scripts/benchmark_latency.py`: Measures full lookup path (normalize + embed + search + verify) over 200 queries against 1k and 10k synthetic entries indexed by real HNSW in PostgreSQL. Saves hardware specs in `data/results/latency.json`.
- **Measured Evaluation Results (Live pgvector):**
  - At default `T_HIT = 0.85`:
    - `no_cache`: Hit rate: 0.0%, Precision: null ("n/a"), False-hit rate: null ("n/a"), LLM calls avoided: 0
    - `exact_match`: Hit rate: 9.0%, Precision: 100%, False-hit rate: 0.0%, Avg lookup: 5.7 ms (p95: 7.9 ms)
    - `semantic_raw`: Hit rate: 37.0%, Precision: 62.0%, **False-hit rate: 38.0% (wrong answers)**, Avg lookup: 30.2 ms
    - `semantic_verified`: Hit rate: 23.0%, **Precision: 100%, False-hit rate: 0.0%**, Avg lookup: 27.3 ms (p95: 45.0 ms)
  - Full Lookup Latency on Live PostgreSQL (HNSW index, 200 queries):
    - 1k scale: Mean = 56.37 ms, p95 = 71.86 ms, p99 = 95.95 ms
    - 10k scale: Mean = 78.50 ms, p95 = 109.52 ms, p99 = 157.88 ms
    - Hardware: Intel64 Family 6 Model 186 (12 logical cores), Windows 11, Python 3.14.0

### [Phase P6 & P7] Hardening, CI, & Final Numbers
- **Status:** Completed
- **Components Implemented:**
  - `lookup_ms` timing window in `semantic_verified.py`: Moved timer stop to after Step 6 (verifier loop) so `lookup_ms` measures normalize + embed + search + verify per PRD §3.
  - Reliability & Determinism suite (`backend/tests/test_reliability.py`):
    - `test_llm_timeout_returns_clean_json_error_and_stores_nothing` (HTTP 502 with clean JSON error; zero cache inserts)
    - `test_llm_general_error_returns_clean_json_error_and_stores_nothing`
    - `test_arena_on_postgres_deterministic` (Deterministic identical results across multiple runs on PostgreSQL)
  - Precision handling: Zero-hit strategies (`no_cache`) output `null` ("n/a") rather than 0%.
  - Custom FastAPI exception handlers formatting errors to `{ "error": { "code": "...", "message": "..." } }` per PRD §7.
- **Test Suite Status:** **57 passed, 0 skipped** (100% test pass rate on live PostgreSQL/pgvector).

---
## Builder 2 Progress

### [Tasks B2-1 to B2-12] Complete Delivery & Verification
- **Status:** 100% Completed & Verified
- **Components Implemented:**
  - **Evaluation Dataset (`data/eval/pairs.jsonl`):**
    - Expanded dataset to exactly **120 human-reviewed query pairs** strictly adhering to `00_MAIN_PRD.md §5.2` and `builder2.md §3`.
    - **Exact Category Breakdown:**
      - `paraphrase`: 46 pairs (Target: ~45, label: `same`)
      - `related_different`: 34 pairs (Target: ~35, label: `different` - hard negatives)
      - `time_sensitive`: 12 pairs (Target: ~12, label: `different` - temporal keywords)
      - `numeric`: 12 pairs (Target: ~12, label: `different` - count/year discrepancies)
      - `ambiguous`: 10 pairs (Target: ~10, label: `different` - polysemous/underspecified)
      - `exact_dup`: 6 pairs (Target: ~6, label: `same` - exact text and casing)
    - Total: 52 `same`, 68 `different`. Zero duplicates, zero schema errors, all queries ≤ 200 chars.
    - Associated documentation: `docs/dataset_notes.md`.
  - **Dataset Validation Test (`backend/tests/test_dataset.py`):**
    - Asserts schema integrity (id, query_a, query_b, label, category, note), string non-emptiness, category distribution targets, and uniqueness.
    - Verified standalone via `python3 backend/tests/test_dataset.py` (ALL VALID).
  - **Modular Frontend Architecture (`frontend/js/`):**
    - Resolved architectural constraint from PRD §11 by extracting inline JavaScript into dedicated client modules:
      - `frontend/js/api.js`: Unified API client managing all `fetch()` requests to `/api/*`.
      - `frontend/js/chat.js`: Interactive console controller, dynamic Decision Inspector updater, cache reset and invalidation handlers.
      - `frontend/js/analytics.js`: Real-time telemetry dashboard, reason-code breakdown renderer.
      - `frontend/js/entries.js`: Cache entry table pagination, status badge formatter, row-level invalidation prompts.
      - `frontend/js/arena.js`: Strategy comparison runner, winner detection, threshold sweep image viewer.
    - Updated all 4 HTML pages (`index.html`, `analytics.html`, `entries.html`, `arena.html`) to cleanly import the modular scripts while maintaining 100% adherence to the PRD §9 DOM ID Contract.
  - **Documentation & Presentation Suite:**
    - `README.md`: Professional project documentation including pitch, decision pipeline diagram, quick start guide, environment variable reference, API table, measured Postgres evaluation results, latency benchmarks, and architectural boundaries.
    - `docs/demo_script.md`: Turn-key 2-minute live demo script detailing roles (Builder 1 delivering / Builder 2 driving), step-by-step actions, and fallback contingency plans.
    - `docs/dataset_notes.md`: Detailed dataset construction, category breakdown, labeling rules, and Arena protocol notes.
    - `docs/bugs.md`: 12-flow QA verification matrix covering initial misses, exact hits, semantic hits, temporal/numeric bypasses, edge cases, zero-hit precision handling, and responsive layout tests.
    - `docs/builder2.md`: Personal PRD synced to `docs/` folder per PRD §11.

