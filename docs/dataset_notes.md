# CacheIQ Evaluation Dataset Notes (`data/eval/pairs.jsonl`)

## 1. Overview
The evaluation dataset is the foundation of CacheIQ's correctness metrics (precision, false-hit rate, recall). It contains **120 human-reviewed query pairs** structured according to `00_MAIN_PRD.md §5.2` and validated by `backend/tests/test_dataset.py`.

Each line is a JSON object with schema:
```json
{"id":"P001","query_a":"...","query_b":"...","label":"same|different","category":"...","note":"..."}
```

## 2. Category Distribution & Target Compliance

| Category | Target (§5.2) | Actual Count | Label | Purpose / Evaluation Role |
|---|---|---|---|---|
| `paraphrase` | ~45 | **46** | `same` | Tests semantic recall on legitimate reformulations and synonyms. |
| `related_different` | ~35 | **34** | `different` | **Hard negatives**: high surface similarity but distinct answers. Tests against false hits. |
| `time_sensitive` | ~12 | **12** | `different` | Real-time temporal queries (`today`, `latest`, `price`). Must bypass cache (Rule V4). |
| `numeric` | ~12 | **12** | `different` | Queries differing only in numbers/years (e.g. 5 vs 10, 2023 vs 2024). Triggers Rule V5. |
| `ambiguous` | ~10 | **10** | `different` | Polysemous words or underspecified queries. Conservative policy: never share answers. |
| `exact_dup` | ~6 | **6** | `same` | Exact or whitespace/case variants tested by Strategy B (Exact SHA-256). |
| **TOTAL** | **≥120** | **120** | **52 same / 68 different** | Balanced coverage for Arena benchmark. |

## 3. Labeling Methodology & Human Review Guidelines
1. **Rule of Conservation:** If there is any doubt whether a single cached answer satisfies both queries completely and accurately, the label is strictly assigned `different`.
2. **Ambiguous Queries:** All polysemous concepts (e.g., "Java the programming language" vs "Java the island", "tree bark" vs "dog bark", "kernel in OS" vs "kernel in agriculture") are labeled `different`.
3. **Hard Negatives:** Questions like *"How to sort a list in Python?"* vs *"How to reverse a list in Python?"* share significant embedding overlap (~0.75-0.85 cos) but produce completely different code answers. These test the verifier and threshold limits.
4. **Temporal Triggers:** Tested against the frozen keyword list from `engine/verifier/time_sensitive.py` (`latest`, `newest`, `current`, `currently`, `today`, `tonight`, `tomorrow`, `yesterday`, `now`, `right now`, `this week`, `this month`, `this year`, `recent`, `recently`, `price`, `weather`, `score`, `news`, `as of`).

## 4. Benchmark Execution in Arena
During an Arena evaluation (`POST /api/arena/run`):
1. For each pair `P<id>`, an isolated execution context is created: `context_key = arena:<run_id>:<pair_id>`.
2. `query_a` is sent first (initial cache miss, LLM answers and stores entry).
3. `query_b` is sent second as the probe query.
4. The outcome of `query_b` is evaluated against `label`:
   - `HIT` on `label: same` → **True Positive** (Valid cache hit)
   - `HIT` on `label: different` → **False Positive / False Hit** (Dangerous wrong answer!)
   - `MISS` on `label: same` → **False Negative** (Missed cache opportunity)
   - `MISS` on `label: different` → **True Negative** (Safe cache miss)

