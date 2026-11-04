# CacheIQ — Explainable Semantic Cache for LLM Apps

> **CacheIQ sits in front of an LLM and answers repeated questions from a vector cache, but only when an independent verifier says the match is safe. It explains every HIT and MISS, and proves with measured numbers how many LLM calls it saved and how many wrong answers it avoided.**

---

## 1. Decision Pipeline

```
query ──► [1 validate + normalize]
              │
        [2 bypass check]  bypass_cache / personalized / time-sensitive ──► MISS (call LLM, do not store)
              │
        [3 exact lookup by exact_key] ──► HIT_EXACT
              │ not found
        [4 embed]  (all-MiniLM-L6-v2, 384-dim, L2-normalised)
              │
        [5 pgvector top-K]  WHERE context_key, ACTIVE, not expired  (ORDER BY distance)
              │
        [6 similarity gate]  best < T_LOW (0.75)  ──► MISS_BELOW_THRESHOLD
                              T_LOW ≤ best < T_HIT ──► MISS_AMBIGUOUS
              │ best ≥ T_HIT (0.85)
        [7 Match Verifier]  rules V1..V5 (pure function, zero search/store imports)
              │ pass                     │ fail → MISS_<reason>
              ▼                          ▼
          HIT_SEMANTIC           [8 call LLM] ──► [9 store entry + embedding] ──► return MISS
```

---

## 2. Prerequisites & Architecture

- **Language:** Python 3.11+
- **Database:** PostgreSQL 16 with `pgvector` extension (Dockerized)
- **Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, L2-normalised unit vectors)
- **Frontend:** Static HTML5 + Tailwind CSS (CDN) + Vanilla JS (served by FastAPI at `/`, zero build step)
- **Docker Usage:** Docker is strictly used for PostgreSQL/pgvector; the backend runs natively on Python.

---

## 3. Quick Start & Setup

### 1. Clone & Configure Environment
```bash
# Copy example configuration (no secrets in repo)
cp .env.example .env
```

### 2. Install Dependencies & Launch Database
```bash
# Install Python packages
make setup

# Start Docker Postgres with pgvector
make db-up

# Run schema migrations (creates vector extension, HNSW index, tables)
make migrate
```

### 3. Launch Application
```bash
# Run FastAPI server on http://localhost:8000
make run
```
Open **http://localhost:8000** in your browser to access the CacheIQ console.

---

## 4. Environment Variables (`.env`)

| Variable | Default Value | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://cacheiq:cacheiq@localhost:5432/cacheiq` | PostgreSQL connection string |
| `LLM_PROVIDER` | `mock` | LLM engine: `mock` (deterministic) or `gemini` (live Google Gemini) |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key (required if `LLM_PROVIDER=gemini`) |
| `ADMIN_KEY` | `changeme` | Header value for `X-Admin-Key` required on admin endpoints |
| `MOCK_LLM_LATENCY_MS` | `1500` | Simulated latency in milliseconds when in mock mode |
| `T_HIT` | `0.85` | Cosine similarity threshold for semantic hit qualification |
| `T_LOW` | `0.75` | Lower boundary for the ambiguous miss band `[0.75, 0.85)` |
| `PRICE_IN` | `0.00000015` | Input price per prompt token ($) |
| `PRICE_OUT` | `0.0000006` | Output price per completion token ($) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer identifier |

### Switching LLM Modes
- **Mock Mode (Default):** Set `LLM_PROVIDER=mock`. Generates deterministic responses in ~1,500 ms (labeled *(simulated)*) without consuming API credits or requiring network connectivity.
- **Gemini Live:** Set `LLM_PROVIDER=gemini` and export your `GEMINI_API_KEY`. Real LLM responses will be generated and cached.

---

## 5. API Reference

All endpoints return JSON. Endpoints are synchronous `def` functions running on FastAPI's threadpool to prevent CPU-blocking during embedding inference.

| Method | Path | Description | Access |
|---|---|---|---|
| `GET` | `/api/health` | Service liveness, DB connection status, loaded model, and LLM mode | Public |
| `POST` | `/api/query` | Primary pipeline: validates, searches, verifies, and returns cached/LLM response | Public |
| `GET` | `/api/stats` | Live telemetry: hits, misses, avoid count, avg latencies, estimated cost saved | Public |
| `GET` | `/api/config` | Read-only configuration: thresholds, model parameters, price assumptions | Public |
| `GET` | `/api/entries` | Paginated cache entry list with created/expires timestamps and hit counts | Public |
| `POST` | `/api/entries/{id}/invalidate` | Manually mark cache entry status as `INVALIDATED` | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/reset` | Truncate cache entries and query log for clean demo reset | Admin (`X-Admin-Key`) |
| `POST` | `/api/arena/run` | Execute 4-strategy benchmark on the 120-pair evaluation dataset | Public |
| `GET` | `/api/arena/latest` | Retrieve results of the most recent Arena benchmark | Public |

---

## 6. Evaluation & Measured Results

Run the full evaluation suite and threshold sweep:
```bash
make eval
```

### Strategy Arena Benchmark (Measured on PostgreSQL pgvector)
Evaluated across our 120-pair labeled dataset (`data/eval/pairs.jsonl`) under threshold $T_{HIT} = 0.85$:

| Strategy | Hit Rate | Precision | False-Hit Rate | Recall (`same`) | Avg Lookup | P95 Lookup | Avoided Calls |
|---|---|---|---|---|---|---|---|
| **A: No Cache** | 0.0% | *n/a* | *n/a* | 0.0% | 0.0 ms | 0.0 ms | 0 |
| **B: Exact Match** | 9.0% | 100.0% | 0.0% | 20.0% | 5.7 ms | 7.9 ms | 3 |
| **C: Semantic Raw** | 37.0% | 62.0% | **38.0% (Wrong Answers)** | 53.0% | 30.2 ms | 37.8 ms | 13 |
| **D: Semantic Verified (CacheIQ)** | 23.0% | **100.0%** | **0.0%** | 53.0% | 27.3 ms | 45.0 ms | 8 |

> **Key Finding:** A bare similarity threshold (`semantic_raw`) suffers an unacceptable **38% false-hit rate**, returning wrong answers for queries with minor numeric or temporal shifts (e.g., *"Top 5"* vs *"Top 10"* scores 0.978 cosine similarity). CacheIQ's **Match Verifier** eliminates all false hits (0.0% false-hit rate, 100% precision) while retaining full semantic recall.

### HNSW Scalability Latency (PostgreSQL 16 + pgvector)
Measured over 200 random probe queries against pre-indexed synthetic datasets (Hardware: Intel Core i7 12-core, Windows 11):

| Vector Index Scale | Mean Lookup Latency | P95 Latency | P99 Latency |
|---|---|---|---|
| **1,000 entries** | 56.37 ms | 71.86 ms | 95.95 ms |
| **10,000 entries** | 78.50 ms | 109.52 ms | 157.88 ms |

*Note: Lookup latency covers the entire pipeline: string normalization + 384-dim embedding inference + pgvector HNSW cosine ranking + multi-rule Match Verifier.*

---

## 7. Project Structure

```
CacheIQ/
 ├── backend/
 │    ├── app/               # FastAPI routing, Pydantic v2 models, config, deps
 │    ├── engine/
 │    │    ├── embedding/    # L2-normalised SentenceTransformer embedder
 │    │    ├── store/        # psycopg pool, parameterised queries, pgvector repo
 │    │    ├── search/       # Semantic search, Unicode NFKC normalizer, SHA-256 keys
 │    │    ├── verifier/     # Independent Match Verifier (Rules V1-V5, time keywords)
 │    │    ├── llm/          # BaseLLM, MockLLM, Gemini LLM adapter
 │    │    ├── strategies/   # Strategies A (NoCache), B (Exact), C (Raw), D (Verified)
 │    │    ├── metrics/      # Telemetry, cost calculations, reason-code stats
 │    │    └── eval/         # Strategy Arena runner, threshold sweep logic
 │    ├── migrations/        # 001_init.sql pgvector schema
 │    └── tests/             # Unit, integration, verifier safety, and dataset tests
 ├── frontend/               # Static web UI (served directly by FastAPI at /)
 │    ├── index.html         # Interactive Chat Console & Real-time Decision Inspector
 │    ├── analytics.html     # System telemetry, savings cards, reason-code breakdown
 │    ├── entries.html       # Active cache entries table & row invalidation
 │    ├── arena.html         # Strategy Arena console & threshold sweep visualization
 │    └── js/                # Modular client scripts (api.js, chat.js, analytics.js, etc.)
 ├── data/
 │    ├── eval/pairs.jsonl   # 120 human-reviewed benchmark query pairs (6 categories)
 │    └── results/           # arena.json, latency.json, sweep.csv, sweep.png
 ├── docs/                   # 00_MAIN_PRD.md, demo_script.md, dataset_notes.md, bugs.md
 ├── scripts/                # proto_cache.py, threshold_sweep.py, benchmark_latency.py
 ├── docker-compose.yml      # PostgreSQL 16 + pgvector container definition
 ├── Makefile                # setup, db-up, migrate, run, test, eval targets
 ├── AGENTS.md               # Architecture rules and system boundaries
 ├── progress.md             # Execution progress log
 └── activeContext.md        # Architecture decisions and current system context
```

---

## 8. Limitations & Honest Scope

1. **Context Boundary:** Cache entries are strictly partitioned by `context_key`. Entries created in tenant/app A will never match tenant/app B.
2. **Dynamic / Personalized Content:** Queries marked `personalized` or matching time-sensitive keywords bypass the cache in both directions (neither read nor stored).
3. **Encryption:** Embeddings are stored unencrypted in pgvector because standard encryption breaks geometric vector search. Database access must be secured at the network/infrastructure layer.
4. **Embedding Model Changes:** If the embedding model is upgraded, existing embeddings become incompatible. Rule V3 detects model mismatches and invalidates candidate reuse.

