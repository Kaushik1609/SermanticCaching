# Builder 2 PRD — Dataset, UI Wiring, Docs, QA (~20%)
Part of CacheIQ. **`00_MAIN_PRD.md` wins any conflict.** Read it first (at least §3, §5.2, §7, §9, §12).

Your work is deliberately independent of the backend: you never wait on Builder 1. From hour 2 you get a **mock API** (`MOCK_API=1`) with realistic fake data, and your dataset and docs need no backend at all.

You own four things: **(1)** the labelled evaluation dataset, **(2)** turning the Stitch design into working pages, **(3)** README and demo material, **(4)** testing the demo flow and reporting bugs.

---

## 1. Task list with gates

| # | Task | Deliverable | Hours | Done when |
|---|---|---|---|---|
| B2-1 | Setup | Clone repo, run `make setup`, run mock API, open `http://localhost:8000/api/health` | 0 to 2 | You can call `POST /api/query` on the mock API |
| B2-2 | Dataset v1 | `data/eval/pairs.jsonl` with 30 pairs | 0 to 4 | File validates with the dataset test |
| B2-3 | Chat page | `frontend/index.html` + `js/api.js`, `js/chat.js` wired to the mock API using the id contract | 2 to 8 | Type a query → badge, similarity, ms, reason appear |
| B2-4 | Dataset v2 | 70 pairs, spread over categories | 4 to 8 | Counts per category printed by the dataset test |
| B2-5 | Switch to real API | Same chat page works against Builder 1's real `/api/query` (turn off `MOCK_API`) | 10 | Real HIT and MISS shown in the browser |
| B2-6 | Analytics + Entries pages | `analytics.html`, `entries.html` with their JS | 8 to 14 | All `#stat-*` and `#entries-*` ids update from real data |
| B2-7 | Dataset final | 120+ pairs, human-reviewed labels, `docs/dataset_notes.md` | 10 to 14 | Targets in main PRD §5.2 met |
| B2-8 | QA pass 1 | `docs/bugs.md` with steps to reproduce for each bug | 14 | Builder 1 has the list |
| B2-9 | Arena page | `arena.html` + `js/arena.js`: Run button, table, winner badges, sweep image | 14 to 18 | Table fills from `/api/arena/latest` |
| B2-10 | README + setup docs | `README.md` body, screenshots, API summary | 14 to 18 | A fresh person can follow it |
| B2-11 | QA pass 2 + freeze | Run the whole demo script 3× in a row, log issues | 18 to 21 | Demo works 3× without a crash |
| B2-12 | Demo material | `docs/demo_script.md`, 90 s fallback screen recording, slides (5 to 6) | 18 to 24 | Rehearsed 3×; both builders can present |

**If you are more than 2 hours late:** tell Builder 1 in chat. Cut in this order: entries page → analytics charts (keep number cards) → Arena sweep image. Never cut the chat page or the dataset.

---

## 2. Files you own
`data/eval/pairs.jsonl` · `frontend/index.html analytics.html entries.html arena.html` · `frontend/js/*` · `docs/*` (except the PRDs) · `README.md` body · `docs/bugs.md`.
Do **not** edit `backend/*`. Found a backend bug? Write it in `docs/bugs.md` and tell Builder 1.

---

## 3. Task details

### B2-2/4/7 — The evaluation dataset (most important task)
This dataset gives the project its correctness numbers (precision, false-hit rate). A wrong label makes the results wrong, so **a human (you) checks every label**.

**Format** (one JSON object per line, UTF-8):
```json
{"id":"P001","query_a":"What is machine learning?","query_b":"Explain machine learning.",
 "label":"same","category":"paraphrase","note":"clear paraphrase"}
```
**Label rule:** `same` means one answer can safely serve both questions. `different` means sharing the answer would be wrong or misleading. If you hesitate, label `different`.

**Targets and examples**
| Category | Count | Label | Example pair |
|---|---|---|---|
| `paraphrase` | ~45 | same | "How do I reverse a list in Python?" / "Python: what's the way to reverse a list?" |
| `related_different` | ~35 | different | "What is Python?" / "How does Python manage memory?" |
| `time_sensitive` | ~12 | different | "What is the latest Python version?" / "What was the latest Python version in 2024?" |
| `numeric` | ~12 | different | "Give me 5 tips for studying" / "Give me 10 tips for studying" |
| `ambiguous` | ~10 | different | "Tell me about Java" / "Tell me about Java island" |
| `exact_dup` | ~6 | same | same text, different casing or extra spaces |

**Good practice:** use a mix of topics (programming, college life, general knowledge, how-to). Avoid personal data. Keep each query under 200 characters. Include hard negatives, where wording is very similar but meaning differs, because they make the benchmark honest.

**Validation test (ask the agent to write it, see prompt B2-P1):** `backend/tests/test_dataset.py` checks JSON validity, unique ids, allowed labels/categories, no empty strings, and prints counts per category. For this one file you may add that single test file; tell Builder 1.

### B2-3/6/9 — Wiring the Stitch design
Builder 1 designs the screens in Google Stitch and puts the raw export in `frontend/design/`. You rebuild the four pages cleanly (do not edit the raw export).

**Rules**
- Plain HTML + Tailwind CDN + vanilla JS. No build step. FastAPI will serve `frontend/` at `/`.
- Every element listed in the main PRD §9 **id contract** must exist with exactly that id.
- `js/api.js` is the only file that calls `fetch`. Base URL is relative (`/api/...`), so there is no CORS setup.
- Show errors visibly (a red message), never fail silently.
- HIT badge: green, text "HIT"; MISS badge: amber, text "MISS". Use text as well as colour.
- If `llm_mode` is `mock`, label MISS latency "simulated" in the UI.
- On HIT, show the matched query line: "Matched: <query> (similarity 0.91)".

**Minimal `api.js` to start from**
```js
const BASE = "/api";
async function call(path, options = {}) {
  const res = await fetch(BASE + path, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || res.statusText);
  return data;
}
export const sendQuery = (query, strategy = "semantic_verified", context_key = "default") =>
  call("/query", { method: "POST", body: JSON.stringify({ query, strategy, context_key }) });
export const getStats = () => call("/stats");
export const getEntries = (limit = 50, offset = 0) => call(`/entries?limit=${limit}&offset=${offset}`);
export const runArena = () => call("/arena/run", { method: "POST" });
export const getArena = () => call("/arena/latest");
export const invalidate = (id, key) => call(`/entries/${id}/invalidate`, { method: "POST", headers: { "X-Admin-Key": key } });
```

### B2-8/11 — QA
Test these 12 flows (mock first, then real), and log anything wrong in `docs/bugs.md` as: *page · steps · expected · actual · screenshot*.
1. Ask a new question → MISS. 2. Ask it again → HIT_EXACT. 3. Ask a paraphrase → HIT_SEMANTIC. 4. Ask "latest …" → MISS_TIME_SENSITIVE. 5. Ask "top 5 …" then "top 10 …" → MISS_NUMERIC_MISMATCH. 6. Empty query → clear error. 7. Very long query → clear error. 8. Stop the backend → UI shows an error, not a blank page. 9. Analytics numbers match what you did. 10. Invalidate an entry → it no longer hits. 11. Run the Arena twice → identical numbers. 12. Phone-width browser → chat page still usable.

### B2-10/12 — README and demo
README sections: what CacheIQ is (3 lines) · architecture diagram (use the pipeline in main PRD §4) · setup (`make setup`, `make db-up`, `make migrate`, `make run`) · how to switch LLM mode · API table · how to run the evaluation (`make eval`) · results (paste from `data/results/`) · limitations (honest list). Only use numbers that exist in `data/results/`; label simulated values.

---

## 4. Stitch handoff (Builder 1 designs; you receive)
Prompt to use in Stitch for the design (Builder 1 may adjust):
```
Design a clean desktop web app called CacheIQ, an explainable semantic cache for LLM apps. Four screens with a
shared top nav (Chat, Analytics, Entries, Arena). One accent colour (teal), white/slate neutrals, rounded cards,
no purple gradients, no robot icons.
1) Chat: left chat log; right panel "Cache decision" with a large HIT (green) or MISS (amber) badge,
similarity percentage, lookup ms, total ms, reason code, one-line explanation, and "Matched: <previous query>".
Query input at the bottom with a Send button and a strategy dropdown.
2) Analytics: 8 number cards (total queries, hits, misses, hit rate, LLM calls made, LLM calls avoided,
avg latency on hit vs miss, estimated cost saved) and a reason-code breakdown list.
3) Entries: table with query, created, expires, hit count, status, and an Invalidate button per row.
4) Arena: a Run button, a 4-row comparison table (No cache, Exact match, Semantic raw, Semantic verified) with
columns precision, false-hit rate, hit rate, recall, avg lookup ms, and winner badges; below it an image area
for a threshold sweep chart.
Make it responsive down to phone width.
```
Export HTML/CSS (or Figma) into `frontend/design/`. Add a short `frontend/design/README.md` noting which export option was used.

---

## 5. Prompts (paste one at a time; confirm each step before the next)

### B2-P1 — Dataset helper (use in any chat model, not Antigravity)
```
I am building an evaluation dataset for a semantic cache. Generate 15 candidate query pairs for category
"<paraphrase | related_different | time_sensitive | numeric | ambiguous>" in this JSON-lines format:
{"id":"","query_a":"","query_b":"","label":"same|different","category":"<category>","note":""}
Rules: topics must mix programming, college life, general knowledge and how-to; each query under 200
characters; no personal data; for related_different include hard negatives where wording is very similar but
the correct answer is different; label "same" only if ONE answer could safely serve both queries, otherwise
"different". Leave id empty. Output only JSON lines.
```
Then **you** review every line, fix labels, remove weak pairs, and assign ids `P001…`.

Then in Antigravity:
```
Read docs/00_MAIN_PRD.md §5.2. Create backend/tests/test_dataset.py that loads data/eval/pairs.jsonl and
asserts: every line is valid JSON with keys id, query_a, query_b, label, category, note; ids are unique;
label in {same, different}; category in {paraphrase, related_different, time_sensitive, numeric, ambiguous,
exact_dup}; no empty strings; query length <= 200. Print the count per category and per label. Do not edit
any other backend file. Update progress.md under the Builder 2 heading.
```

### B2-P2 — Chat page against the mock API
```
Read docs/00_MAIN_PRD.md §6.2, §7 and §9, and docs/builder2.md §3. Use Planning mode.
Look at frontend/design/ for the Stitch export (read only, do not modify it). Create frontend/index.html
(plain HTML + Tailwind CDN, no build step), frontend/js/api.js (the only file that calls fetch; relative
base /api) and frontend/js/chat.js. Rebuild the Chat screen cleanly with EXACTLY these ids: query-input,
send-btn, chat-log, strategy-select, badge-outcome, val-similarity, val-lookup-ms, val-total-ms,
val-reason, val-explain, val-matched. On send: POST /api/query, append user and answer to the chat log,
update the decision panel. HIT = green badge with text "HIT", MISS = amber badge with text "MISS". Show
visible error messages for failed requests or empty input. If llm_mode is "mock", label MISS latency
"(simulated)". Test by running the backend with MOCK_API=1 and opening http://localhost:8000.
Definition of done: a query shows badge, similarity, both latencies, reason and explanation. Update progress.md.
```
(Builder 1 serves `frontend/` from FastAPI at hour 2 to 4. Until then open the file with a local static server such as `python -m http.server` and set the API base in `api.js` to `http://localhost:8000/api`; switch it back to `/api` once the mount exists.)

### B2-P3 — Analytics and Entries pages
```
Read docs/00_MAIN_PRD.md §6.2 (stats, entries) and §9. Create frontend/analytics.html + js/analytics.js and
frontend/entries.html + js/entries.js, using the same nav and styles as index.html. Required ids: analytics:
stat-total, stat-hits, stat-misses, stat-hit-rate, stat-avoided, stat-made, stat-lat-hit, stat-lat-miss,
stat-saved, reason-list. entries: entries-body, entries-total. Analytics refreshes every 5 seconds and shows
the cost assumptions text under the "saved" card. Entries has an Invalidate button per row that asks for the
admin key with prompt(), calls POST /api/entries/{id}/invalidate with header X-Admin-Key, then reloads.
Handle errors visibly. Definition of done: all ids update from the mock API; update progress.md.
```

### B2-P4 — Arena page
```
Read docs/00_MAIN_PRD.md §5 and §6.2 (arena). Create frontend/arena.html + js/arena.js with ids arena-run,
arena-body, arena-winner, arena-sweep-img. On load fetch /api/arena/latest and fill a 4-row table (strategy,
precision, false-hit rate, hit rate, recall, avg lookup ms, p95 lookup ms, LLM calls avoided). The Run button
calls POST /api/arena/run, shows a loading state, then refreshes. Highlight the best value per column and show
winner badges. Show data/results/sweep.png in arena-sweep-img if it exists (hide the element otherwise).
Show "mock LLM (simulated latency)" when llm_mode is mock. Update progress.md.
```

### B2-P5 — README
```
Read docs/00_MAIN_PRD.md and the repo Makefile. Write README.md sections: what CacheIQ is (3 lines), pipeline
diagram (ASCII from main PRD §4), prerequisites (Python 3.11, Docker for Postgres only), setup commands
(make setup, make db-up, make migrate, make run), .env variables (names only, no secrets), how to switch
LLM mode, API table, how to run evaluation (make eval), results (copy only numbers that exist in
data/results/, label simulated values), limitations, project structure. Test every command by following the
README from a fresh clone and fix anything that fails. Update progress.md.
```

---

## 6. Your viva checklist (be able to explain)
1. What the dataset measures and why labels must be human-checked.
2. The difference between a `paraphrase` and a `related_different` pair, with one example each.
3. What HIT, MISS and each reason code mean.
4. Why the UI labels some latency "simulated".
5. How the pages get data (`api.js` → `/api/...`).
