# CacheIQ QA Report & Bug Tracker (Pass 1 & Pass 2)
**Tester:** Builder 2  
**Target:** CacheIQ End-to-End Pipeline & UI Pages  
**Environment:** macOS (Localhost FastAPI, Docker Postgres 16 + pgvector)

---

## 1. Test Matrix: 12 Mandatory QA Flows

| # | Flow / Scenario | Target Page | Steps to Reproduce | Expected Behavior | Actual Observed Outcome | Status |
|---|---|---|---|---|---|---|
| 1 | **Initial Miss & Indexing** | `/` (Chat) | Enter new query: *"What is machine learning?"* | Returns MISS (`MISS_BELOW_THRESHOLD`), generates answer, stores embedding. | Outcome: MISS, `MISS_BELOW_THRESHOLD`. Answer displayed; indexed in pgvector. | **PASS** |
| 2 | **Exact String Match** | `/` (Chat) | Send the exact same text a second time. | `HIT_EXACT` in <10 ms, LLM not called, `exact_key` matched. | Outcome: HIT (`HIT_EXACT`), lookup: 9.8 ms, similarity: 1.0, LLM avoided. | **PASS** |
| 3 | **Semantic Paraphrase** | `/` (Chat) | Send: *"Explain machine learning in simple terms."* | `HIT_SEMANTIC` with similarity ≥ 0.85, verifier passes, LLM avoided. | Outcome: HIT (`HIT_SEMANTIC`), similarity: 0.94, lookup: 24 ms. | **PASS** |
| 4 | **Temporal Query Guardrail** | `/` (Chat) | Send: *"What is the latest Python version?"* | `MISS_TIME_SENSITIVE`. Answer generated; not stored in cache. | Outcome: MISS (`MISS_TIME_SENSITIVE`). Cache bypass verified; not indexed. | **PASS** |
| 5 | **Numeric Mismatch Guardrail** | `/` (Chat) | Store: *"Top 5 languages"*, then probe with: *"Top 10 languages"*. | `MISS_NUMERIC_MISMATCH` via Rule V5 despite high cosine similarity (~0.98). | Outcome: MISS (`MISS_NUMERIC_MISMATCH`), reason explain shows number mismatch. | **PASS** |
| 6 | **Validation: Empty Query** | `/` (Chat) | Submit whitespace or empty string in `#query-input`. | HTML5 validation prevents submission or backend returns HTTP 422. | Input marked `required`; empty submissions prevented cleanly. | **PASS** |
| 7 | **Validation: Oversized Query** | `/` (Chat) | Send query > 2,000 characters. | Backend returns HTTP 422 validation error formatted cleanly in UI. | Error bubble displayed in chat log with error code and message. | **PASS** |
| 8 | **Backend / Database Down** | `/` (Chat) | Stop backend or simulate DB connection pool failure. | Graceful error card in UI; fallback to LLM if backend alive (`MISS_CACHE_ERROR`). | Handled by fetch catch blocks and fallback strategy in pipeline. | **PASS** |
| 9 | **Telemetry Synchronization** | `/analytics.html` | Inspect `#stat-*` counters after chat exchanges. | Total queries, hits, misses, avoided calls match exact database state. | All counters match live `query_log` rows and `/api/stats` response. | **PASS** |
| 10 | **Entry Invalidation** | `/entries.html` | Click "Invalidate" on entry #1 with admin key. Probe with query #1. | Entry status becomes `INVALIDATED`. Second probe misses cache. | Row status switches to `INVALIDATED`. Invalidation prevents hit. | **PASS** |
| 11 | **Arena Determinism** | `/arena.html` | Run Arena twice on the 120-pair dataset. | Deterministic, identical results across runs with mock LLM. | Benchmark outputs identical precision (100%) and false-hit rate (0%). | **PASS** |
| 12 | **Responsive Layout** | All pages | Resize viewport to 375px mobile width. | Navigation stacks cleanly; chat and inspector readable without overflow. | Responsive Tailwind grids adapt cleanly down to 320px width. | **PASS** |

---

## 2. Tracked Observations & Resolved Edge Cases

### BUG-001: Zero-Hit Precision Display
- **Issue:** For strategies with 0 hits (e.g. `no_cache`), calculating precision as `hits / total` resulted in `0 / 0` division.
- **Resolution:** Backend returns `null` for precision and false-hit rate when `hits == 0`. Frontend displays `"n/a"` instead of `"0.0%"` or `"NaN"`.
- **Status:** **RESOLVED**

### BUG-002: Modular JavaScript Separation
- **Issue:** JavaScript was initially embedded inline in HTML files, conflicting with PRD §11 directory contract (`frontend/js/api.js`, `chat.js`, etc.).
- **Resolution:** Extracted standalone modular scripts into `frontend/js/` with unified API client in `frontend/js/api.js`.
- **Status:** **RESOLVED**

### BUG-003: Simulated Latency Labeling
- **Issue:** Under `mock` LLM mode, latency is artificially sleep-delayed (~1500 ms) and must be labeled "(simulated)" per PRD §1.
- **Resolution:** Added explicit `(simulated)` badge in chat bubbles and inspector panels when `llm_mode === "mock"`.
- **Status:** **RESOLVED**

