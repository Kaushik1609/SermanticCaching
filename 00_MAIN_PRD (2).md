# CacheIQ — Explainable Semantic Cache for LLM Apps
**Main PRD · Version 2.0** (supersedes v1.0 "Intelligent Semantic Caching System")
Team: **Builder 1** (backend, algorithms, evaluation, ~80%) · **Builder 2** (eval dataset, UI wiring, docs, QA, ~20%)
Format: **24-hour build** (assumed; if the real timeline is longer, keep the gates in order and rescale the hours, see §13)

> **One-line pitch:** *CacheIQ sits in front of an LLM and answers repeated questions from a vector cache, but only when an independent verifier says the match is safe. It explains every HIT and MISS, and proves with measured numbers how many LLM calls it saved and how many wrong answers it avoided.*

---

## 0. How to read these docs
1. `00_MAIN_PRD.md` (this file) is the single source of truth: contracts, algorithms, scope.
2. `builder1.md` and `builder2.md` are personal PRDs: tasks, hour gates, files owned, paste-ready Antigravity prompts.
3. If a personal PRD conflicts with this file, **this file wins**. Change this file first, then tell the other builder.

---

## 1. Review of v1.0

### Keep (it was good)
- Focused standalone cache first. RAG, Redis and encryption stay later.
- Python + FastAPI + Sentence Transformers + PostgreSQL/pgvector. Right stack, one language.
- "Prefer a MISS over a wrong answer." This is the core idea and drives the whole design.
- Evaluate correctness (precision, false-hit rate) together with speed and cost.

### Gaps and fixes
| # | Gap in v1.0 | Fix in v2.0 |
|---|---|---|
| 1 | "Check threshold and relevant context" was never made concrete. | **Two-stage decision**: similarity gate, then an independent **Match Verifier** with fixed rules and reason codes (§4). |
| 2 | No baseline to prove semantic caching is worth it. | **Cache Arena**: 4 strategies (no cache, exact match, raw semantic, verified semantic) benchmarked on the same labelled dataset (§5). |
| 3 | Evaluation data was undefined. | Labelled **pair dataset** (JSONL, ≥120 pairs, 6 categories) with a fixed format (§5.2). |
| 4 | Demo and tests depended on LLM quota and network. | **Mock LLM** mode (deterministic answer, simulated latency, clearly labelled "simulated") plus real Gemini/Ollama for the live demo. |
| 5 | Streamlit UI. The UI is now designed in Google Stitch, which exports HTML/CSS, not Streamlit code. | UI is **static HTML + Tailwind + vanilla JS served by FastAPI** (decision D1, §9). |
| 6 | Thresholds listed (0.70 to 0.90) but no reproducible method. | `scripts/threshold_sweep.py` writes CSV + chart from the labelled dataset, seeded. |
| 7 | "Estimated cost savings" was vague. | Explicit formula with labelled price assumptions (§5.3). |
| 8 | Context isolation said "where applicable". | `context_key` is a **SQL filter applied before ranking**; it is never a post-check. |
| 9 | Embedding is CPU-blocking inside an async API. | Endpoints are plain `def` (FastAPI runs them in a threadpool) and the model loads once at startup (warm-up call). |
| 10 | Time-sensitive answers: "avoid caching unless freshness is checked." | Concrete rule: time-sensitive queries **bypass** the cache both ways (not read, not stored) (§4.3). |
| 11 | Migrations "should be used". | Plain numbered `.sql` migrations and a tiny runner. Alembic is overkill for 24 hours. |

---

## 2. Cross-check: existing solutions, uniqueness

### 2.1 Existing solutions (verify current details before quoting them in the pitch)
| Category | Examples | Good at | Missing vs our goal |
|---|---|---|---|
| Open-source semantic caches | GPTCache (Zilliz), RedisVL SemanticCache | Plug-in caching, many vector backends | Mostly one similarity threshold. Little explainability or measured false-hit reporting. |
| Framework caches | LangChain / LlamaIndex LLM caches | Easy to enable | Usually exact-match or a thin semantic layer. No verifier, no analytics. |
| Gateway caches | LLM gateway/proxy products | Zero-code caching | Mostly exact-match. Closed behaviour. |
| Papers / blogs | Semantic caching write-ups | Ideas | No working, measured, explainable demo. |

**The gap we fill:** an *open, explainable, measured* semantic cache: **embed → search → verify → HIT/MISS with a reason → measured savings and measured wrong-answer rate.**

### 2.2 Uniqueness (our edge vs other teams)
1. **Match Verifier**: a similarity score alone is never trusted; independent rules gate every hit.
2. **Reason codes** with plain-English explanations for every HIT and MISS.
3. **Cache Arena**: no cache vs exact vs raw semantic vs verified semantic on one labelled dataset.
4. **Threshold sweep chart**: shows the hit-rate vs false-hit trade-off, so the chosen threshold is justified by data.
5. **Deterministic replay**: seeded dataset plus mock LLM means the demo never depends on luck or network.
6. **Only measured numbers** are shown. Anything simulated is labelled "simulated".

---

## 3. Core definitions (everyone uses exactly these)
- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, output **L2-normalised** (length 1).
- **Similarity** = `1 − cosine_distance` (pgvector `<=>` returns distance). Range about 0 to 1 for normal text.
- **Normalization** (`normalize(q)`): Unicode NFKC, trim, collapse whitespace. Casing is **kept** for the embedding. Lowercasing is used **only** for the exact-match key.
- **exact_key** = `sha256(lower(normalize(q)) + "|" + context_key + "|" + config_hash)`.
- **config_hash** = `sha256(provider | model | temperature | system_prompt)`. A cached answer is reusable only under the same config.
- **context_key:** scope of reuse (app, tenant, knowledge base). Default `"default"`. Entries never cross contexts.
- **Thresholds (starting points, tuned by the sweep):** `T_HIT = 0.85`, `T_LOW = 0.75`. Similarity in `[T_LOW, T_HIT)` is the **ambiguous band** and is treated as a MISS.
- **Top-K** = 5 candidates from pgvector, verified in rank order. The first one that passes verification wins.
- **TTL:** default 7 days (`expires_at`). `NULL` means no expiry.
- **Status lifecycle:** `ACTIVE → INVALIDATED` (manual). Expired entries are filtered at query time.
- **Latency:** `lookup_ms` = normalize + embed + search + verify. `total_ms` = whole request including the LLM call if made.

### 3.1 Reason codes (frozen)
| Code | Outcome | Meaning |
|---|---|---|
| `HIT_EXACT` | HIT | Same normalized text, context and config. |
| `HIT_SEMANTIC` | HIT | Best candidate ≥ `T_HIT` and passed the verifier. |
| `MISS_NO_CANDIDATE` | MISS | Nothing stored in this context. |
| `MISS_BELOW_THRESHOLD` | MISS | Best similarity < `T_LOW`. |
| `MISS_AMBIGUOUS` | MISS | Best similarity in `[T_LOW, T_HIT)`. |
| `MISS_TIME_SENSITIVE` | MISS | Query asks about "latest / today / price / news …". Cache bypassed. |
| `MISS_NUMERIC_MISMATCH` | MISS | Numbers or years differ between the two queries. |
| `MISS_CONFIG_MISMATCH` | MISS | Candidate was generated under a different LLM config or embedding model. |
| `MISS_EXPIRED` | MISS | Candidate was past `expires_at`. |
| `MISS_BYPASS` | MISS | Caller set `bypass_cache` or `personalized`. |
| `MISS_CACHE_ERROR` | MISS | DB/lookup failed. Fell back to the LLM, nothing stored. |

---

## 4. Decision pipeline (the heart of the project)

```
query ──► [1 validate + normalize]
              │
        [2 bypass check]  bypass_cache / personalized / time-sensitive ──► MISS (call LLM, do not store*)
              │
        [3 exact lookup by exact_key] ──► HIT_EXACT
              │ not found
        [4 embed]
              │
        [5 pgvector top-K]  WHERE context_key, ACTIVE, not expired  (ORDER BY distance)
              │
        [6 similarity gate]  best < T_LOW → MISS_BELOW_THRESHOLD
                              T_LOW ≤ best < T_HIT → MISS_AMBIGUOUS
              │ best ≥ T_HIT
        [7 Match Verifier]  rules V1..V5 (no import from search code)
              │ pass                     │ fail → MISS_<reason>
              ▼                          ▼
          HIT_SEMANTIC           [8 call LLM] → [9 store entry + embedding] → return MISS
```
\* Time-sensitive and personalized responses are never stored.

### 4.1 Stage details
1. **Validate:** non-empty, ≤ 2,000 chars, strip control characters. Else HTTP 422.
2. **Exact lookup:** one indexed SQL lookup on `exact_key`. Cheapest path, and it is also **strategy B**.
3. **Search SQL** (frozen):
```sql
SELECT id, query_text, response_text, embedding_model, config_hash, expires_at,
       1 - (query_embedding <=> %(q)s) AS similarity
FROM cache_entries
WHERE context_key = %(ctx)s AND status = 'ACTIVE'
ORDER BY query_embedding <=> %(q)s
LIMIT 5;
```
Expiry and config are checked by the verifier (not in SQL) so each rejection gets its own reason code.

### 4.2 Match Verifier (independent module)
Pure function. **No import from `engine/search`.** Input: `new_query`, `candidate`, `request_config_hash`, `now`. Output: `Verdict{ok, reason_code, explain}`. Rules run in this order, the first failure wins:
| Rule | Check | Reason code |
|---|---|---|
| V1 | `candidate.expires_at` is null or in the future | `MISS_EXPIRED` |
| V2 | `candidate.config_hash == request_config_hash` | `MISS_CONFIG_MISMATCH` |
| V3 | `candidate.embedding_model == current model` | `MISS_CONFIG_MISMATCH` |
| V4 | `is_time_sensitive(new_query) == False` and the same for `candidate.query_text` | `MISS_TIME_SENSITIVE` |
| V5 | set of digit sequences in `new_query` == set in `candidate.query_text` | `MISS_NUMERIC_MISMATCH` |

### 4.3 Time-sensitive detector (frozen v1)
Case-insensitive match on whole words/phrases: `latest, newest, current, currently, today, tonight, tomorrow, yesterday, now, right now, this week, this month, this year, recent, recently, price, weather, score, news, as of`. Words live in `engine/verifier/time_sensitive.py` as one list so Builder 2's dataset tests can import it. Years (`19xx/20xx`) are handled by V5.

### 4.4 Strategies (Cache Arena) — all implement one interface `Strategy.handle(query, ctx) -> QueryResponse`
| Id | Name | Behaviour | Role |
|---|---|---|---|
| A | `no_cache` | Always call the LLM. | Baseline for cost and latency |
| B | `exact_match` | `exact_key` lookup only. | Traditional cache baseline |
| C | `semantic_raw` | Exact, then top-1 with `similarity ≥ T_HIT`. No verifier, no ambiguous band. | Shows why a bare threshold is risky |
| D | `semantic_verified` (**default**) | Full pipeline in §4. | Our product |

---

## 5. Evaluation (owner: Builder 1 code, Builder 2 dataset)

### 5.1 Metrics (all computed from the same labelled dataset)
| Metric | Definition |
|---|---|
| Hit rate | HITs ÷ probe queries |
| Cache precision | correct HITs ÷ all HITs (correct = pair labelled `same`) |
| False-hit rate | wrong HITs ÷ all HITs (= 1 − precision) |
| Recall on `same` pairs | `same` pairs that produced a HIT ÷ all `same` pairs |
| Lookup latency | mean and p95 of `lookup_ms` (real, measured) |
| LLM calls avoided | HIT count |
| Latency reduction | measured lookup latency vs LLM latency. Mock LLM latency is labelled **simulated**; a small real-Gemini sample is labelled **measured**. |
| Estimated cost saved | see §5.3 |

### 5.2 Dataset format (frozen) — `data/eval/pairs.jsonl`, one JSON object per line
```json
{"id":"P001","query_a":"What is machine learning?","query_b":"Explain machine learning.",
 "label":"same","category":"paraphrase","note":"clear paraphrase"}
```
- `label`: `same` (answer can be safely shared) or `different` (must not be shared).
- `category` (6 values): `paraphrase`, `related_different`, `time_sensitive`, `numeric`, `ambiguous`, `exact_dup`.
- Targets: ≥ 120 pairs: ~45 paraphrase, ~35 related_different, ~12 time_sensitive, ~12 numeric, ~10 ambiguous, ~6 exact_dup.
- `ambiguous` pairs are labelled `different` (conservative: when in doubt, do not share).
- Labels are **human-reviewed**. A model may draft candidates, but a person confirms every label.

**Arena protocol:** for each pair, use an isolated `context_key = arena:<run_id>:<pair_id>`. Send `query_a` (miss, stored), then `query_b` (probe). Record the outcome of `query_b`. Mock LLM is used so runs are deterministic. A separate benchmark preloads 1k / 10k synthetic entries to measure lookup latency at scale.

### 5.3 Cost formula (assumptions shown in the UI)
`saved = Σ over HITs of (prompt_tokens × price_in + completion_tokens × price_out)`. `price_in` and `price_out` come from config and must be checked against the provider's pricing page on demo day. Local embedding cost is treated as ₹0/$0 but compute is mentioned as an assumption. If real token usage is missing (mock LLM), use fixed assumed token counts, labelled "assumed".

---

## 6. Data contract (frozen at hour 2 — Builder 1 owns `backend/app/models.py` and `migrations/`)

### 6.1 Database (migration `001_init.sql`)
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE cache_entries (
  id                BIGSERIAL PRIMARY KEY,
  context_key       TEXT        NOT NULL DEFAULT 'default',
  query_text        TEXT        NOT NULL,
  exact_key         CHAR(64)    NOT NULL,
  query_embedding   VECTOR(384) NOT NULL,
  response_text     TEXT        NOT NULL,
  embedding_model   TEXT        NOT NULL,
  config_hash       CHAR(64)    NOT NULL,
  prompt_tokens     INT,
  completion_tokens INT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at        TIMESTAMPTZ,
  hit_count         INT         NOT NULL DEFAULT 0,
  status            TEXT        NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INVALIDATED'))
);
CREATE UNIQUE INDEX uq_exact_active ON cache_entries (exact_key) WHERE status = 'ACTIVE';
CREATE INDEX idx_ctx_status ON cache_entries (context_key, status);
CREATE INDEX idx_embedding_hnsw ON cache_entries USING hnsw (query_embedding vector_cosine_ops);

CREATE TABLE query_log (            -- no query text stored (privacy)
  id             BIGSERIAL PRIMARY KEY,
  ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
  context_key    TEXT NOT NULL,
  strategy       TEXT NOT NULL,
  outcome        TEXT NOT NULL,     -- HIT | MISS
  reason_code    TEXT NOT NULL,
  similarity     REAL,
  lookup_ms      REAL,
  total_ms       REAL,
  llm_called     BOOLEAN NOT NULL,
  prompt_tokens  INT,
  completion_tokens INT,
  matched_entry_id BIGINT
);
```

### 6.2 JSON shapes
```jsonc
// POST /api/query  — request
{ "query": "Can you define machine learning?", "context_key": "default",
  "strategy": "semantic_verified", "bypass_cache": false, "personalized": false }

// response
{ "answer": "Machine learning is ...",
  "outcome": "HIT",                       // HIT | MISS
  "hit_type": "SEMANTIC",                 // EXACT | SEMANTIC | null
  "reason_code": "HIT_SEMANTIC",
  "explain": "Matched 'What is machine learning?' (similarity 0.91 ≥ 0.85). All checks passed.",
  "similarity": 0.91,
  "matched_query": "What is machine learning?",
  "matched_entry_id": 12,
  "llm_called": false,
  "lookup_ms": 18.4, "total_ms": 19.1,
  "strategy": "semantic_verified",
  "embedding_model": "all-MiniLM-L6-v2",
  "llm_mode": "mock" }                    // mock | gemini | ollama

// GET /api/stats
{ "total_queries": 120, "hits": 54, "misses": 66, "hit_rate": 0.45,
  "avg_lookup_ms": 21.7, "avg_total_ms_hit": 22.0, "avg_total_ms_miss": 1620.3,
  "llm_calls_made": 66, "llm_calls_avoided": 54,
  "est_cost_saved": 0.84, "cost_assumptions": "assumed tokens, price from config",
  "by_reason": {"HIT_SEMANTIC": 40, "HIT_EXACT": 14, "MISS_AMBIGUOUS": 9} }

// GET /api/entries
{ "items": [ { "id": 12, "query_text": "...", "created_at": "...", "expires_at": null,
               "hit_count": 4, "status": "ACTIVE", "context_key": "default" } ], "total": 31 }

// POST /api/arena/run  → GET /api/arena/latest
{ "run_id": "r42", "dataset_size": 128, "thresholds": {"T_HIT":0.85,"T_LOW":0.75},
  "llm_mode": "mock",
  "rows": [ { "strategy": "semantic_verified", "hit_rate": 0.41, "precision": 0.98,
              "false_hit_rate": 0.02, "recall_same": 0.88, "avg_lookup_ms": 20.1,
              "p95_lookup_ms": 31.0, "llm_calls_avoided": 52, "est_cost_saved": 0.78 } ],
  "winner": { "precision": "semantic_verified", "hit_rate": "semantic_raw" } }

// Error shape (all endpoints)
{ "error": { "code": "VALIDATION_ERROR", "message": "query must not be empty" } }
```

---

## 7. API
| Method | Path | Purpose | Owner |
|---|---|---|---|
| GET | `/api/health` | liveness, DB ok, model loaded, `llm_mode` | B1 |
| POST | `/api/query` | the main endpoint (§6.2) | B1 |
| GET | `/api/stats` | live counters | B1 |
| GET | `/api/entries?limit&offset` | list cache entries | B1 |
| POST | `/api/entries/{id}/invalidate` | mark INVALIDATED (needs `X-Admin-Key` header) | B1 |
| POST | `/api/admin/reset` | clear cache + logs for a clean demo (needs `X-Admin-Key`) | B1 |
| POST | `/api/arena/run` | run strategies A to D on the dataset | B1 |
| GET | `/api/arena/latest` | last arena result | B1 |
| GET | `/api/config` | thresholds, model, llm_mode, price assumptions (read-only) | B1 |

**Mock mode:** `MOCK_API=1` makes every endpoint return fixtures from `backend/tests/fixtures/*.json`. Builder 1 ships this at **hour 2** so Builder 2 can build the UI immediately.

---

## 8. Scope
**Must (hour 0 to 14):** embeddings, pgvector search, exact + semantic pipeline, Match Verifier, mock LLM + one real LLM, `/api/query`, `/api/stats`, query_log, labelled dataset, chat UI with HIT/MISS badge, similarity and latency.
**Should (14 to 18):** Cache Arena + chart, threshold sweep, entries page + invalidate, analytics page, reason-code explanations, latency benchmark at 1k/10k entries, CI.
**Stretch (only if all gates are green):** TTL editing in UI, second embedding model comparison, dark/light toggle, SSE live stats.
**Out:** Redis, RAG, application-level encryption, multi-region, custom embedding training, auth/accounts, Docker for the app itself (Docker is used for Postgres only).

---

## 9. UI spec (design: Google Stitch · wiring: Builder 2)

**D1 — Decision:** Stitch exports HTML/CSS (and can export to Figma), not Streamlit components. So the UI is **static HTML + Tailwind (CDN) + vanilla JS**, served by FastAPI via `StaticFiles` from `frontend/`. Same origin, so no CORS setup. Streamlit is dropped.

**Pages**
| Page | File | Must contain |
|---|---|---|
| Chat | `frontend/index.html` | query box, send, chat log, HIT/MISS badge, similarity %, lookup/total ms, reason code + explanation, "matched query" line on hits, strategy dropdown |
| Analytics | `frontend/analytics.html` | cards (total, hits, misses, hit rate, LLM calls made/avoided, avg latency hit vs miss, est. cost saved), reason-code breakdown |
| Entries | `frontend/entries.html` | table of entries, created/expires, hit count, Invalidate button (asks for admin key) |
| Arena | `frontend/arena.html` | Run button, 4-row table (precision, false-hit, hit rate, recall, latency), winner badges, threshold-sweep image |

**DOM id contract (Stitch export must be wired to these ids; Builder 2 adds them):**
`#query-input #send-btn #chat-log #strategy-select #badge-outcome #val-similarity #val-lookup-ms #val-total-ms #val-reason #val-explain #val-matched` · analytics: `#stat-total #stat-hits #stat-misses #stat-hit-rate #stat-avoided #stat-made #stat-lat-hit #stat-lat-miss #stat-saved #reason-list` · entries: `#entries-body #entries-total` · arena: `#arena-run #arena-body #arena-winner #arena-sweep-img`.

**Look:** clean, one accent color, rounded cards, a clear green HIT and amber MISS badge (text label as well as colour), no purple-gradient/robot clichés, readable at mobile width.

---

## 10. Tech stack (final)
Python 3.11, FastAPI, Pydantic v2, `sentence-transformers`, PostgreSQL 16 + pgvector (Docker image `pgvector/pgvector:pg16`, Postgres only), `psycopg[binary]` 3 + `pgvector` Python package, `google-genai` (Gemini) or `httpx` to Ollama, NumPy / Pandas / Matplotlib for evaluation, pytest + hypothesis, GitHub Actions CI. Frontend: HTML, Tailwind CDN, vanilla JS, optional Chart.js CDN.

## 11. Folder structure (create this first)
```
cacheiq/
 ├── backend/
 │    ├── app/               (main.py, routes.py, models.py, config.py, deps.py)         ← B1
 │    ├── engine/
 │    │    ├── embedding/    (embedder.py)                                               ← B1
 │    │    ├── store/        (db.py, repo.py, migrate.py)                                ← B1
 │    │    ├── search/       (semantic_search.py)                                        ← B1
 │    │    ├── verifier/     (verifier.py, time_sensitive.py)                            ← B1
 │    │    ├── llm/          (base.py, mock_llm.py, gemini.py, ollama.py)                ← B1
 │    │    ├── strategies/   (no_cache.py, exact_match.py, semantic_raw.py, semantic_verified.py) ← B1
 │    │    ├── metrics/      (stats.py, cost.py)                                         ← B1
 │    │    └── eval/         (arena.py, sweep.py)                                        ← B1
 │    ├── migrations/        (001_init.sql)                                              ← B1
 │    └── tests/             (unit, integration, fixtures/)                              ← B1 (B2 adds dataset tests)
 ├── frontend/
 │    ├── design/            (raw Stitch export, untouched)                              ← B1 exports, B2 reads
 │    ├── index.html analytics.html entries.html arena.html                              ← B2
 │    └── js/                (api.js, chat.js, analytics.js, entries.js, arena.js)       ← B2
 ├── data/
 │    ├── eval/pairs.jsonl                                                               ← B2
 │    └── results/           (arena.json, sweep.csv, sweep.png)                          ← B1
 ├── scripts/                (threshold_sweep.py, benchmark_latency.py, seed_demo.py)    ← B1
 ├── docs/                   (this PRD, builder PRDs, demo_script.md, README assets)     ← B2
 ├── docker-compose.yml  .env.example  Makefile  AGENTS.md  README.md                   ← B1 (README body: B2)
 ├── progress.md             (Antigravity-maintained, one heading per builder)
 └── activeContext.md        (Antigravity-maintained: decisions, structure, future scope)
```
`progress.md` and `activeContext.md` are written by Antigravity, never by hand. Update `progress.md` after every step and `activeContext.md` whenever a decision changes.

## 12. Demo script (2 minutes — Builder 1 delivers, Builder 2 drives)
1. **0:00 Problem (15 s):** the same question asked 3 ways costs 3 LLM calls. Show the first query: MISS, ~1.5 s (label "simulated" in mock mode, or live Gemini).
2. **0:15 Hit (25 s):** ask a paraphrase: HIT_SEMANTIC, similarity 0.9, ~20 ms, "LLM calls avoided: 1".
3. **0:40 Safety (30 s):** ask "What is the latest Python version?", then a different year variant. Both bypass or miss with a reason code. "We prefer a MISS over a wrong answer."
4. **1:10 Arena (30 s):** table: no cache vs exact vs raw semantic vs verified. Point at false-hit rate: raw semantic has false hits, verified has far fewer. Show the threshold sweep chart.
5. **1:40 Analytics (20 s):** hit rate, LLM calls avoided, estimated cost saved (assumptions visible).
**Fallback:** pre-recorded 90 s screen capture plus screenshots (Builder 2).

## 13. Acceptance tests and timeline

### 13.1 Acceptance tests (must pass before freeze)
- [ ] Same query twice → second is `HIT_EXACT` and the LLM is not called.
- [ ] Paraphrase pair above `T_HIT` → `HIT_SEMANTIC`, `llm_called=false`.
- [ ] Similarity in `[T_LOW, T_HIT)` → `MISS_AMBIGUOUS`.
- [ ] Query with "latest"/"today"/"price" → `MISS_TIME_SENSITIVE`, and the response is **not** stored.
- [ ] "top 5 …" vs "top 10 …" → `MISS_NUMERIC_MISMATCH`.
- [ ] Entry in context A is never returned to context B.
- [ ] Expired or INVALIDATED entry is never returned.
- [ ] Different `config_hash` → `MISS_CONFIG_MISMATCH`.
- [ ] DB down → request still answered by the LLM with `MISS_CACHE_ERROR`, no crash.
- [ ] LLM down/timeout → clear JSON error, nothing half-stored.
- [ ] Verifier module has no import from `engine/search` (checked by a test).
- [ ] Arena on the dataset is deterministic: same dataset + mock LLM → identical numbers.
- [ ] `semantic_verified` false-hit rate ≤ `semantic_raw` false-hit rate on the dataset (or we show honestly when it is not).
- [ ] No API key or query text appears in logs.
- [ ] Fresh clone → `make setup && make run` works in under 10 minutes.
- [ ] Every DOM id in §9 exists and updates from real API data.

### 13.2 Timeline and gates
| Hours | Builder 1 | Builder 2 | Gate |
|---|---|---|---|
| 0 to 2 | Repo, docker-compose, models.py + SQL frozen, mock API with fixtures | Reads PRDs, sets up repo, starts dataset (first 30 pairs) | Both run the project; contract signed |
| 2 to 6 | Embedder, in-memory prototype, DB + pgvector, exact + semantic search | Dataset to 70 pairs; receives Stitch export; builds chat page against mock API | Each part passes its own tests alone |
| 6 to 10 | Pipeline + mock LLM + `/api/query` + query_log | Chat page on real API; analytics page on mock `/api/stats` | Type a query in the browser → HIT/MISS with reason |
| 10 to 14 | Verifier, Gemini LLM, stats, entries + invalidate | Dataset to 120+ pairs, entries page, QA pass 1 | Safety demo (time-sensitive, numeric) works |
| 14 to 18 | Arena, threshold sweep, latency benchmark, CI | Arena page, README draft, QA pass 2 | Judge understands the value without reading code |
| 18 to 21 | **Feature freeze.** Bug fixes, seed demo data, tag `demo-stable` | Bug bash, record fallback video | Demo repeatable 3× in a row |
| 21 to 24 | Final numbers, tag | Deck, rehearsal ×3, final README | Clean clone runs; both can explain every part |

**Rules:** (1) Nothing merges to `main` without `pytest` green. (2) Branch per builder: `feat/b1-<topic>`, `feat/b2-<topic>`. (3) Tag `demo-stable` at hours 10, 14, 18, 21. (4) If a task is more than 2 h late, say so in chat and cut scope.

---

## 14. Risks
| Risk | Response |
|---|---|
| Wrong cache hits | Verifier + ambiguous band + measured false-hit rate; prefer MISS. |
| pgvector install pain | Docker for Postgres only; CI uses the same image. |
| Gemini quota/network | Mock LLM default for tests and arena; live Gemini only for the demo, with fallback video. |
| Model first-load slowness | Load and warm up at startup; health endpoint shows `model_loaded`. |
| Dataset too easy/small | Mix categories, include hard negatives; report counts per category. |
| Builder 2 blocked | Mock API at hour 2; dataset and QA are independent of the backend. |
| Stitch export messy | Keep raw export in `frontend/design/`; Builder 2 rebuilds pages cleanly against the id contract. |
| Overclaiming savings | Only measured numbers; simulated/assumed values are labelled. |

## 15. Judge / viva Q&A cheat sheet
- *Why not just exact-match caching?* It misses rephrasings. The Arena shows the extra hits and what they cost in false hits.
- *Why not trust the similarity score?* Different questions can score high (e.g. "Python 3.11" vs "Python 3.12"). The verifier and ambiguous band exist for that.
- *How did you pick 0.85?* From the threshold sweep on a labelled dataset. It is a starting point for this workload, not a universal value.
- *What is cosine similarity?* The angle between two embedding vectors. We normalise vectors to length 1, so cosine equals the dot product.
- *Is it safe across users?* Entries are filtered by `context_key` in SQL before ranking. Personalized queries bypass the cache.
- *What about stale answers?* TTL, manual invalidation, and time-sensitive queries bypass the cache.
- *Why not encrypt embeddings?* Standard encryption destroys vector geometry, so searchable encrypted embeddings are out of scope. Sensitive text encryption is a later release.
- *Does it scale?* HNSW index; we measured lookup latency at 1k and 10k entries. Beyond that is future work.

## 16. Security checklist (Builder 1)
API keys only in `.env` (git-ignored, `.env.example` committed) · admin endpoints need `X-Admin-Key` · query text not logged by default · request size limit + rate limit on `/api/query` · parameterised SQL only · LLM timeout 20 s · HTTPS in any deployment.

## 17. References
- pgvector: https://github.com/pgvector/pgvector
- Sentence Transformers: https://www.sbert.net/
- GPTCache: https://github.com/zilliztech/GPTCache
- FastAPI static files: https://fastapi.tiangolo.com/tutorial/static-files/
- Google Stitch (UI design): verify current export options before the hackathon
