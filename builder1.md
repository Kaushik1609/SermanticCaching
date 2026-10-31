# Builder 1 PRD — Backend, Algorithms, Evaluation (~80%)
Part of CacheIQ. **`00_MAIN_PRD.md` wins any conflict.** Read it first.

You own the system's brain: embeddings, pgvector, the pipeline, the Match Verifier, the LLM layer, the API, the Arena and all measured numbers. You also own the frozen contract (`models.py`, `001_init.sql`, fixtures) that Builder 2 depends on.

---

## 1. How to work in Antigravity
- **Planning mode** for P2, P3, P4 (database, pipeline, verifier). Read the plan before approving it.
- **Fast mode** for small edits and bug fixes.
- **Manager view (parallel agents)** only in P5 and P6, after the API contract is frozen: one agent for Arena, one for benchmark/CI.
- Put the rules below in `AGENTS.md` at the repo root (and paste them into Antigravity's workspace rules if you use that feature).
- Ask the agent to update `progress.md` after every phase and `activeContext.md` when a decision changes. Do not hand-write them.
- Review every diff yourself before committing. You must be able to explain every file in a viva.

### `AGENTS.md` (paste as-is)
```
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
```

---

## 2. Math to code in plain words (your Phase 1 understanding)
- An embedding is a list of 384 numbers that places a sentence as a point/arrow in space. Similar meaning means the arrows point the same way.
- **Cosine similarity** measures the angle between two arrows: 1 means same direction, 0 means unrelated.
- If both arrows are scaled to length 1 (**normalised**), cosine similarity is just the **dot product**: multiply matching numbers and add them up.
- pgvector's `<=>` gives **cosine distance** = `1 − similarity`, so we convert back with `1 - (a <=> b)`.
```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def embed(text: str) -> np.ndarray:
    return model.encode(text, normalize_embeddings=True)   # length-1 vector, 384 numbers

def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))                             # dot product = cosine for unit vectors

print(similarity(embed("What is machine learning?"), embed("Explain machine learning.")))  # high
print(similarity(embed("What is Python?"), embed("What is the latest Python version?")))   # lower
```

---

## 3. Task list with gates

| # | Phase | Deliverable | Hours | Done when |
|---|---|---|---|---|
| P0 | Scaffold + contract | Repo, folders, `docker-compose.yml`, `.env.example`, Makefile, `models.py`, `001_init.sql`, fixtures, **mock API** (`MOCK_API=1`) | 0 to 2 | Builder 2 can run the mock API and get every endpoint in §7 of the main PRD |
| P1 | Embeddings + in-memory prototype | `embedder.py`, `scripts/proto_cache.py` with cosine and threshold | 2 to 4 | Paraphrase pair scores above 0.85, related-different pair below, tests pass |
| P2 | Persistent store | Migration runner, `repo.py`, exact lookup, pgvector top-K search | 4 to 7 | Insert and search work against Docker Postgres; context isolation test passes |
| P3 | Pipeline + LLM + API | `mock_llm.py`, `gemini.py` (or `ollama.py`), strategies B and D (basic), `/api/query`, `query_log`, `/api/stats`, `/api/health` | 7 to 11 | Browser (Builder 2's chat page) shows HIT/MISS with reason on real data |
| P4 | Match Verifier | `verifier.py`, `time_sensitive.py`, rules V1 to V5, reason codes and explanations, bypass rules | 11 to 14 | Safety acceptance tests pass (time-sensitive, numeric, config, expiry) |
| P5 | Evaluation | Strategies A and C, `arena.py`, `/api/arena/*`, `threshold_sweep.py`, `benchmark_latency.py`, entries + invalidate + reset endpoints | 14 to 18 | Arena table and sweep chart produced from `pairs.jsonl`; deterministic |
| P6 | Hardening | CI (GitHub Actions with `pgvector/pgvector:pg16`), security checklist, error paths (DB down, LLM down), seed demo script | 18 to 21 | All acceptance tests in main PRD §13.1 green; tag `demo-stable` |
| P7 | Final numbers | Final arena + sweep results saved in `data/results/`, demo rehearsal | 21 to 24 | Numbers in the deck match `data/results/` |

**You must deliver to Builder 2:** mock API at hour 2 · real `/api/query`, `/api/stats` at hour 10 · `/api/entries` and `/api/arena/*` at hour 18 · Stitch export in `frontend/design/` by hour 2 to 4.

**If you are more than 2 hours late:** drop in this order: ollama support → latency benchmark at 10k → threshold sweep chart (keep the CSV) → strategy C. Never drop the verifier or the dataset-based arena.

---

## 4. Files you own
`backend/app/*` · `backend/engine/*` · `backend/migrations/*` · `backend/tests/*` · `scripts/*` · `docker-compose.yml` · `.env.example` · `Makefile` · `AGENTS.md` · `data/results/*`.
You do **not** edit `frontend/*.html`, `frontend/js/*`, `data/eval/pairs.jsonl` (Builder 2 owns them). You may read them.

---

## 5. Key implementation notes
- **Warm-up:** call `embed("warm up")` at startup so the first user request is not slow.
- **pgvector registration:** `from pgvector.psycopg import register_vector` on each connection; pass embeddings as `np.ndarray`.
- **Exact key:** `sha256(lower(normalize(q)) + "|" + ctx + "|" + config_hash)`. Compute once, use for lookup and insert.
- **Top-K loop:** iterate candidates in rank order; the first one passing the verifier wins. If the best candidate fails V5 but the second would pass, that is acceptable. Log the reason of the **best** candidate for explanations.
- **Hit counting:** on a HIT, `UPDATE hit_count = hit_count + 1` in the same transaction as the log row.
- **DB failure:** catch at the strategy level; return `MISS_CACHE_ERROR`, call the LLM, store nothing.
- **Mock LLM:** answer = `f"[mock answer] {query}"` plus a fixed fake token count; sleeps a configured `MOCK_LLM_LATENCY_MS` (default 1500) and the response says `llm_mode: "mock"`. UI/analytics must label this latency "simulated".
- **Real LLM:** one provider behind `LLM.generate(prompt) -> (text, prompt_tokens, completion_tokens)`; 20 s timeout; key from env var.
- **Arena isolation:** per-pair `context_key = arena:<run_id>:<pair_id>`; delete those rows after the run (or mark INVALIDATED) so the live cache stays clean.
- **Determinism:** no randomness in strategies; any sampling in the benchmark uses a fixed seed.
- **Do not log** `query_text`, `response_text` or keys. `query_log` is already text-free.

---

## 6. Antigravity prompts (paste one at a time, confirm each phase before the next)

### P0 — Scaffold and contract
```
Read docs/00_MAIN_PRD.md and docs/builder1.md fully before acting. Use Planning mode.
Task P0: create the repo structure from main PRD §11, docker-compose.yml (service `db` using image
pgvector/pgvector:pg16, port 5432, volume, env from .env), .env.example (DATABASE_URL, LLM_PROVIDER=mock,
GEMINI_API_KEY=, ADMIN_KEY=, MOCK_LLM_LATENCY_MS=1500, T_HIT=0.85, T_LOW=0.75), a Makefile with targets
setup, db-up, migrate, run, test. Create backend/migrations/001_init.sql exactly as in main PRD §6.1, a tiny
migration runner, and backend/app/models.py with Pydantic v2 models for every JSON shape in §6.2.
Implement MOCK_API=1: every endpoint in §7 returns realistic fixtures from backend/tests/fixtures/*.json
and mount the frontend/ folder as static files AFTER all API routes using
StaticFiles(directory="frontend", html=True), so http://localhost:8000 serves frontend/index.html once it exists
(create a placeholder index.html saying "CacheIQ"). Add pytest tests that the fixtures validate against models.
Constraints: follow AGENTS.md; no extra frameworks; endpoints are plain `def`.
Definition of done: `make db-up && make migrate && MOCK_API=1 make run` works and `make test` is green.
Update progress.md (Builder 1 heading). Do not touch frontend/*.html.
```

### P1 — Embeddings + in-memory prototype
```
Task P1. Implement backend/engine/embedding/embedder.py: load sentence-transformers/all-MiniLM-L6-v2 once,
`embed(text) -> np.ndarray` (normalize_embeddings=True), `embed_many`, a `warm_up()` function and model name
constant. Create scripts/proto_cache.py: an in-memory cache (list of (query, embedding, response)) with
lookup by dot-product similarity and a configurable threshold, runnable as `python scripts/proto_cache.py`
that prints similarity for 8 sample pairs (paraphrases and related-but-different) and HIT/MISS at T_HIT.
Add tests: identical text scores ~1.0; a paraphrase pair > 0.80; unrelated pair < 0.40; vectors have length 1.
Add comments connecting cosine similarity to the dot product of unit vectors, in plain language.
Definition of done: tests green, script output pasted into progress.md.
```

### P2 — Persistent store
```
Task P2 (Planning mode). Implement backend/engine/store/db.py (connection pool via psycopg_pool, pgvector
registered) and repo.py with: insert_entry, get_by_exact_key, search_top_k(embedding, context_key, k=5)
using EXACTLY the SQL in main PRD §4.1, increment_hit, invalidate(id), list_entries(limit, offset),
count, reset_all. Parameterised SQL only. Add integration tests against the Docker Postgres:
insert then exact lookup; insert 5 entries then top-K ordering; context_key isolation (entry in ctx A is
never returned for ctx B); INVALIDATED entries are never returned; unique exact_key among ACTIVE rows.
Definition of done: `make test` green with the DB running; progress.md updated.
```

### P3 — Pipeline, LLM and API
```
Task P3 (Planning mode). Implement: engine/llm/base.py (abstract LLM.generate -> text, prompt_tokens,
completion_tokens), mock_llm.py (deterministic answer, sleeps MOCK_LLM_LATENCY_MS, fixed fake token
counts, reports llm_mode="mock"), gemini.py (google-genai SDK, key from env, 20 s timeout).
Implement strategies/exact_match.py (B) and strategies/semantic_verified.py (D) WITHOUT the verifier yet:
normalize -> bypass check -> exact lookup -> embed -> top-K -> similarity gate (T_LOW/T_HIT, ambiguous band)
-> HIT or call LLM and store. Return the QueryResponse shape from main PRD §6.2 with correct reason codes and
plain-English `explain`. Write a query_log row for every request. Implement routes: POST /api/query,
GET /api/stats (hits, misses, rate, avg latencies, calls made/avoided, est_cost_saved with labelled
assumptions, by_reason), GET /api/health, GET /api/config. Handle DB failure -> MISS_CACHE_ERROR fallback.
Disable MOCK_API for real routes (keep MOCK_API=1 working).
Tests: same query twice = HIT_EXACT and llm not called; paraphrase = HIT_SEMANTIC; ambiguous band = MISS.
Definition of done: curl POST /api/query works end to end; tests green; progress.md updated.
```

### P4 — Match Verifier
```
Task P4 (Planning mode). Implement engine/verifier/time_sensitive.py (the word list from main PRD §4.3,
exported as one constant list plus is_time_sensitive(text)) and engine/verifier/verifier.py with
verify(new_query, candidate, request_config_hash, now, current_model) -> Verdict(ok, reason_code, explain)
implementing rules V1..V5 in the exact order of main PRD §4.2. The verifier MUST NOT import from
engine/search or engine/store (add a test that scans imports). Wire it into semantic_verified: bypass cache
(read and store) when the query is time-sensitive, bypass_cache or personalized is true. Add explanations such
as "Numbers differ: query has {5}, cached query has {10}."
Tests (table-driven, at least 20 cases): expired, config mismatch, model mismatch, time-sensitive words,
numeric mismatch (5 vs 10, 2023 vs 2024), paraphrase passes, query without numbers passes.
Definition of done: all main PRD §13.1 safety tests green; progress.md updated.
```

### P5 — Evaluation (Manager view: run the two agents in parallel)
```
Agent 1 — Task P5a: implement strategies/no_cache.py (A) and strategies/semantic_raw.py (C: exact then top-1
similarity >= T_HIT, no verifier, no ambiguous band). Implement engine/eval/arena.py: read data/eval/pairs.jsonl
(format in main PRD §5.2), for each pair use an isolated context_key arena:<run_id>:<pair_id>, send query_a then
query_b for each strategy A-D using the mock LLM, compute hit_rate, precision, false_hit_rate, recall_same,
mean and p95 lookup_ms, llm_calls_avoided, est_cost_saved. Routes: POST /api/arena/run, GET /api/arena/latest.
Save results to data/results/arena.json. Clean up arena rows afterwards. Deterministic output required.
Agent 2 — Task P5b: scripts/threshold_sweep.py: for T_HIT in 0.70..0.95 step 0.05 (T_LOW = T_HIT - 0.10)
compute hit_rate, precision, false_hit_rate for strategies C and D on the dataset; write data/results/sweep.csv
and a Matplotlib chart sweep.png. scripts/benchmark_latency.py: preload 1k and 10k synthetic entries (fixed
seed) and report mean/p95 lookup latency; write data/results/latency.json.
Definition of done: both scripts run with `make eval`; results are reproducible; progress.md updated.
```

### P6 — Hardening and CI
```
Task P6. Add GET /api/entries, POST /api/entries/{id}/invalidate and POST /api/admin/reset protected by the
X-Admin-Key header (value from env). Add request size limit and a simple per-IP rate limit on /api/query.
Add GitHub Actions workflow running pytest with a pgvector/pgvector:pg16 service container.
Test failure paths: DB down -> MISS_CACHE_ERROR; LLM timeout -> clean JSON error and nothing stored.
Verify no API keys or query text in logs. Add scripts/seed_demo.py that resets the cache and preloads 10 demo
entries. Run the full acceptance checklist from main PRD §13.1 and list any failing item in progress.md.
```

---

## 7. Your viva checklist (be able to explain)
1. What an embedding is and why normalised vectors make cosine = dot product.
2. Why `1 - (a <=> b)` is the similarity.
3. How HNSW speeds up search and why we also filter by `context_key`.
4. Why the verifier is a separate module and what each rule catches.
5. How the threshold was chosen (sweep chart) and why it is workload-specific.
6. What is simulated (mock LLM latency) vs measured (lookup latency).
