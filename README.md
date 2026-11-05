# CacheIQ — Explainable Semantic Cache for LLM Apps

> **CacheIQ sits in front of an LLM and answers repeated or semantically equivalent questions from a vector cache — but only when an independent verifier guarantees the match is safe. It explains every HIT and MISS with explicit reason codes, and proves with measured numbers how many LLM calls it saved and how many wrong answers it prevented.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL 16 + pgvector](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791.svg)](https://github.com/pgvector/pgvector)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 1. Why CacheIQ? The Problem with Plain Semantic Caching

Standard semantic caching uses a single similarity threshold (e.g., cosine similarity $\ge 0.85$). While intuitive, this approach produces **dangerous false hits**:

* *"Top 5 programming languages in 2024"* vs. *"Top 10 programming languages in 2024"* has **0.978 cosine similarity** — yet serving the cached answer gives the user half the list they asked for.
* *"What is the stock price of Apple today?"* vs. *"What was the stock price of Apple yesterday?"* scores **>0.92**, but financial queries must never be served from a stale cache.
* *"How to sort a list in Python?"* vs. *"How to reverse a list in Python?"* overlaps heavily in vocabulary but requires opposite code.

**CacheIQ solves this with a two-stage decision pipeline: a dual-threshold similarity gate followed by an isolated Match Verifier.**

---

## 2. Decision Pipeline & Architecture

```
User Query
    │
    ▼
[1. Validate & Normalize] (Unicode NFKC, whitespace collapsed, case preserved for embedding)
    │
    ├─► [2. Bypass Check] ──► Time-sensitive / Personalized / bypass_cache?
    │                           └── Yes ──► MISS (Call LLM; do NOT cache answer)
    │
    ├─► [3. Exact Lookup] ──► SHA-256 exact_key match in PostgreSQL?
    │                           └── Yes ──► HIT_EXACT (0 ms LLM, ~5 ms DB)
    │
    ▼
[4. Vector Embedding] (all-MiniLM-L6-v2, 384 dimensions, L2-normalised unit vector)
    │
    ▼
[5. Top-K HNSW Search] (PostgreSQL pgvector <=> cosine distance, filtered by context_key)
    │
    ▼
[6. Dual-Threshold Similarity Gate]
    ├── similarity < T_LOW (0.75)  ─────────► MISS_BELOW_THRESHOLD
    ├── T_LOW ≤ similarity < T_HIT (0.85) ──► MISS_AMBIGUOUS (Safety fallback to LLM)
    └── similarity ≥ T_HIT (0.85) ─────────► [7. Match Verifier]
                                                 │
                     ┌───────────────────────────┴───────────────────────────┐
                     ▼                                                       ▼
            Passed All Rules (V1–V5)                                 Failed Any Rule
                     │                                                       │
                     ▼                                                       ▼
               HIT_SEMANTIC                                             MISS_<REASON>
       (Serve verified cached answer)                            (Call LLM & update cache)
```

### Match Verifier Rules (Strict Order of Execution)
The Match Verifier is a pure function with **zero dependencies on the vector index or database**:

| Rule | Check | Triggered Reason Code | Explanation |
| :---: | :--- | :--- | :--- |
| **V1** | Expiry Check | `MISS_EXPIRED` | Cached entry has exceeded its `expires_at` timestamp. |
| **V2** | Config Consistency | `MISS_CONFIG_MISMATCH` | Entry was generated under different LLM settings (model, temperature, prompt). |
| **V3** | Embedding Model Check | `MISS_CONFIG_MISMATCH` | Candidate vector was created using a different embedding model. |
| **V4** | Temporal Filter | `MISS_TIME_SENSITIVE` | Query contains real-time keywords (*today, price, weather, latest, news*). |
| **V5** | Numeric & Year Invariance | `MISS_NUMERIC_MISMATCH` | Digit sequences or years differ (*"Top 5"* vs *"Top 10"*, *"2023"* vs *"2024"*). |

### Complete Reason Codes
* `HIT_EXACT`: Identical normalized text, context, and LLM configuration.
* `HIT_SEMANTIC`: Best candidate $\ge T_{HIT}$ and passed all Match Verifier rules.
* `MISS_NO_CANDIDATE`: Cache is completely empty for this `context_key`.
* `MISS_BELOW_THRESHOLD`: Highest similarity is $< T_{LOW}$ (0.75).
* `MISS_AMBIGUOUS`: Similarity falls in the uncertainty band $[0.75, 0.85)$. Cached answer withheld for safety.
* `MISS_NUMERIC_MISMATCH`: Similarity was high, but quantities, versions, or dates do not match.
* `MISS_TIME_SENSITIVE`: Query asks about live or shifting data; bypasses cache in both directions.
* `MISS_CONFIG_MISMATCH`: Generated under a different LLM provider, prompt, or temperature.
* `MISS_EXPIRED`: Candidate passed TTL.
* `MISS_BYPASS`: Client explicitly requested `bypass_cache=true` or `personalized=true`.
* `MISS_CACHE_ERROR`: Database offline or unreachable; smoothly fails over to direct LLM response.

---

## 3. Four Caching Strategies Compared

CacheIQ includes the **Cache Arena**, an automated benchmarking engine that pits 4 strategies against each other:

1. **`no_cache` (Baseline A):** Every request queries the LLM directly. Establishes the latency and cost ceiling.
2. **`exact_match` (Baseline B):** Traditional key-value cache (SHA-256 of normalized text). Fast (5 ms) and 100% precise, but completely misses rewordings and paraphrases.
3. **`semantic_raw` (Baseline C):** Standard vector search with a bare similarity threshold ($T_{HIT} = 0.85$). Captures paraphrases, but suffers from high false-hit rates on numbers and temporal queries.
4. **`semantic_verified` (CacheIQ Product):** Dual-threshold gate + Match Verifier. Delivers the high hit rates of semantic search while virtually eliminating false hits.

---

## 4. Measured Evaluation Results

All numbers below were measured against a live PostgreSQL 16 instance with the `pgvector` extension.

### A. Realistic Traffic Simulation (1,000 Requests, Zipfian Popularity $\alpha=1.1$, Seed 42)
Simulates realistic production traffic where a subset of questions is popular, probed strictly against the independent **TEST split** (60 pairs, 94 distinct intents):

| Strategy | Hit Rate | Precision | False Hits (Wrong Answers) | LLM Calls Made | LLM Avoided | Mean Lookup | p95 Lookup | Assumed Cost Saved | Simulated Time Saved |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`no_cache`** | 0.0% | *n/a* | 0 | 1,000 | 0 | 0.0 ms | 0.0 ms | \$0.0000 | 0.0 s |
| **`exact_match`** | 88.9% | 100.0% | **0** | 111 | 889 | 5.7 ms | 8.5 ms | \$0.0232 | 1,333.5 s |
| **`semantic_raw`** | 91.4% | 95.84% | **38** | 86 | 914 | 17.7 ms | 61.5 ms | \$0.0238 | 1,371.0 s |
| **`semantic_verified` (CacheIQ)** | 88.7% | **98.42%** | **14** *(63% reduction)* | 113 | 887 | 15.0 ms | 52.2 ms | \$0.0231 | 1,330.5 s |

> **Key Takeaway:** Bare semantic caching (`semantic_raw`) served **38 wrong answers** to users. CacheIQ's `semantic_verified` pipeline **eliminated 63% of false hits** while preserving an 88.7% hit rate and saving over 22 minutes of LLM compute time.

### B. HNSW Index Scalability Latency (PostgreSQL 16 pgvector)
Lookup latency encompasses: *string normalization + 384-dim embedding + pgvector HNSW cosine ranking + multi-rule verification*:

| Cache Size (HNSW Index) | Mean Full-Path Latency | p95 Latency | p99 Latency |
| :--- | :---: | :---: | :---: |
| **1,000 Entries** | **56.3 ms** | 71.9 ms | 96.0 ms |
| **10,000 Entries** | **78.5 ms** | 109.5 ms | 157.9 ms |

---

## 5. Quick Start Guide

### Prerequisites
* Python 3.11+
* Docker Desktop (for PostgreSQL with `pgvector`)

### 1. Clone & Set Environment
```bash
git clone https://github.com/Kaushik1609/SermanticCaching.git
cd SermanticCaching

# Create .env from template
cp .env.example .env
```

### 2. Start PostgreSQL with pgvector
```bash
# Start Dockerized Postgres (pgvector/pgvector:pg16 on port 5432)
make db-up

# Run initial migrations (creates vector extension, schema, HNSW indexes)
make migrate
```

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4. Start the Application Server
```bash
# Starts Uvicorn server on http://127.0.0.1:8080 (or port 8000)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8080 --reload
```

Open your browser to: **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)**

---

## 6. Web Console Tour

CacheIQ provides 4 clean web interfaces served directly by FastAPI (zero Node/npm build steps):

1. **Interactive Chat & Decision Inspector (`/`):** Test live queries in real time. Displays instant HIT/MISS badges, similarity percentage, exact lookup latency, and an explanation of the verifier's decision.
2. **Cache Arena (`/arena.html`):** Side-by-side benchmarking of all 4 caching strategies with automated winner badges and threshold sweep charts.
3. **Telemetry & Analytics (`/analytics.html`):** Live dashboard showing queries served, LLM calls avoided, cumulative cost savings, and reason-code distribution.
4. **Cache Entries Inspector (`/entries.html`):** Inspect active cached responses, view hit counts, and manually invalidate stale entries with admin authentication.

---

## 7. Makefile & CLI Commands

| Command | Action |
| :--- | :--- |
| `make db-up` | Launches PostgreSQL 16 container with `pgvector`. |
| `make db-down` | Stops the PostgreSQL container. |
| `make migrate` | Applies SQL migrations to initialize the vector database. |
| `make test` | Runs the full `pytest` suite (**65 tests passing**). |
| `make eval` | Runs the threshold sweep and HNSW latency benchmark. |
| `make traffic` | Executes the 1,000-request Zipf traffic simulation and outputs `traffic.png`. |
| `make run` | Starts the local development server. |

---

## 8. Configuration Reference (`.env`)

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://cacheiq:cacheiq@localhost:5432/cacheiq` | PostgreSQL connection URL. |
| `LLM_PROVIDER` | `mock` | `mock` (deterministic, zero cost) or `gemini` (live Google Gemini API). |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key (needed only when `LLM_PROVIDER=gemini`). |
| `ADMIN_KEY` | `changeme` | Secret key for invalidation and admin reset endpoints. |
| `T_HIT` | `0.85` | Cosine similarity threshold required to trigger semantic match verification. |
| `T_LOW` | `0.75` | Lower threshold boundary; $[T_{LOW}, T_{HIT})$ triggers `MISS_AMBIGUOUS`. |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformer model (384-dimensional unit vector). |
| `PRICE_IN` | `0.00000015` | Price per prompt token in USD (\$0.15 / 1M tokens). |
| `PRICE_OUT` | `0.0000006` | Price per completion token in USD (\$0.60 / 1M tokens). |

---

## 9. API Reference

All endpoints return structured JSON. Endpoints are synchronous `def` functions running on FastAPI's threadpool to prevent CPU inference blocking.

| Method | Endpoint | Description | Auth |
| :---: | :--- | :--- | :---: |
| `GET` | `/api/health` | Service liveness, PostgreSQL connectivity, model status, and LLM mode. | None |
| `POST` | `/api/query` | Primary pipeline: search, verify, return HIT or forward to LLM on MISS. | None |
| `GET` | `/api/stats` | Live telemetry aggregated from `query_log` (hits, misses, cost saved). | None |
| `GET` | `/api/config` | Read-only configuration values (thresholds, model, pricing rules). | None |
| `GET` | `/api/entries` | Paginated cache entry list with created/expires timestamps and hit counts. | None |
| `POST` | `/api/entries/{id}/invalidate` | Invalidate an entry so it will no longer be matched. | `X-Admin-Key` |
| `POST` | `/api/admin/reset` | Clear cache entries and query log for a clean benchmark run. | `X-Admin-Key` |
| `POST` | `/api/arena/run` | Execute 4-strategy evaluation on the pair dataset. | None |
| `GET` | `/api/arena/latest` | Retrieve the latest Cache Arena benchmark results. | None |

---

## 10. Repository Structure

```
CacheIQ/
 ├── backend/
 │    ├── app/               # FastAPI routing, Pydantic v2 schemas, configuration
 │    ├── engine/
 │    │    ├── embedding/    # L2-normalised SentenceTransformer embedder (singleton)
 │    │    ├── store/        # psycopg 3 connection pool, parameterised queries, pgvector repo
 │    │    ├── search/       # Top-K vector search, Unicode NFKC normalizer, SHA-256 keys
 │    │    ├── verifier/     # Isolated Match Verifier (Rules V1..V5; zero store imports)
 │    │    ├── llm/          # BaseLLM, MockLLM, and Google Gemini integration
 │    │    ├── strategies/   # Strategies A (NoCache), B (Exact), C (Raw), D (Verified)
 │    │    ├── metrics/      # Telemetry aggregation, cost calculation, reason breakdown
 │    │    └── eval/         # Live PostgreSQL Cache Arena evaluator & split manager
 │    ├── migrations/        # 001_init.sql (vector extension, tables, HNSW indexes)
 │    └── tests/             # 65 automated tests (pipeline, verifier, reliability, traffic sim)
 ├── frontend/               # Static web client served directly by FastAPI at /
 │    ├── index.html         # Interactive Chat Console & Real-time Decision Inspector
 │    ├── analytics.html     # Live Metrics Dashboard & Telemetry Cards
 │    ├── entries.html       # Cache Entry Browser & Manual Invalidation
 │    ├── arena.html         # Strategy Arena Benchmark & Sweep Visualizer
 │    └── js/                # Modular vanilla JavaScript (api.js, chat.js, arena.js, etc.)
 ├── data/
 │    ├── eval/pairs.jsonl   # 120 human-labeled benchmark query pairs (6 categories)
 │    └── results/           # arena.json, latency.json, sweep.csv, sweep.png, traffic.png
 ├── scripts/
 │    ├── traffic_sim.py     # Deterministic 1,000-request Zipf traffic simulation
 │    ├── threshold_sweep.py # Threshold tuning sweep across T_HIT values
 │    └── benchmark_latency.py # Scale latency benchmark on 1k and 10k vectors
 ├── docker-compose.yml      # PostgreSQL 16 + pgvector container definition
 ├── Makefile                # Standard developer targets (db-up, migrate, test, traffic, run)
 ├── AGENTS.md               # Strict architectural boundaries and project rules
 ├── progress.md             # Antigravity progress log
 └── activeContext.md        # Architectural decisions and current system context
```

---

## 11. Design Principles & Honest Boundaries

1. **Context Isolation:** Cache entries are strictly segregated by `context_key` at the SQL query level before ranking. Tenant A cannot match or access Tenant B's cache.
2. **Privacy First:** User prompt strings are **never** logged to `query_log`; only hashes, latencies, tokens, and reason codes are retained.
3. **Fail-Safe Fallback:** If the vector database is unreachable, queries are transparently answered directly by the LLM (`MISS_CACHE_ERROR`) without interruption.
4. **No Encrypted Vectors:** Vectors are stored unencrypted in pgvector because standard encryption destroys geometric distance relationships. Access control is enforced at the network and database tier.
5. **Deterministic Testing:** Seeded mock LLM mode allows 100% reproducible benchmarking without external network dependencies or API token costs.
