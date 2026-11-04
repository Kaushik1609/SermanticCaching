# CacheIQ Demo Script (2-Minute Pitch & Walkthrough)
**Roles:** Builder 1 Delivers (Technical context & metrics) · Builder 2 Drives (Browser interaction & console navigation)
**Target Duration:** 2 minutes (120 seconds)

---

### Step 1: The Problem & Baseline Miss [0:00 – 0:15] (15 seconds)
- **Speaker:** "Large language models are expensive, slow, and non-deterministic. When users ask semantically identical questions, LLM applications waste tokens and time generating redundant answers."
- **Driver Action:**
  1. Open the Chat page (`/`). Point out the **HNSW Vector Index** and **Live Telemetry** badges.
  2. In the query box, enter:
     ```
     What is machine learning?
     ```
  3. Click **Send** (or press Enter).
- **Driver Highlights:**
  - Decision Inspector shows **MISS** (`MISS_BELOW_THRESHOLD`).
  - Total latency is **~1,500 ms** (mock simulated LLM latency) or live Gemini generation.
  - LLM was called. Entry is indexed with a 384-dimensional unit vector in pgvector.

---

### Step 2: Instant Semantic Hit [0:15 – 0:40] (25 seconds)
- **Speaker:** "Traditional caches require an exact string match. CacheIQ understands semantic meaning. When another user asks the same question in different words, we resolve it in milliseconds without touching the LLM."
- **Driver Action:**
  1. Enter the paraphrase:
     ```
     Explain machine learning in simple terms.
     ```
  2. Click **Send**.
- **Driver Highlights:**
  - Inspector shows vivid green **HIT** badge (`HIT_SEMANTIC`).
  - Similarity score: **~0.91 – 0.94** (exceeding threshold `0.85`).
  - Matched query: *"What is machine learning?"* (Entry #1).
  - Lookup latency: **~20 – 35 ms** (a ~50x speedup!).
  - Telemetry: **LLM Calls Avoided: 1**, estimated cost saved updated.

---

### Step 3: Safety, Verifier, and Numeric Guardrails [0:40 – 1:10] (30 seconds)
- **Speaker:** "The core danger of vector caching is false hits: returning an answer that sounds similar but is factually wrong. CacheIQ operates under a strict principle: **We prefer a MISS over a wrong answer**."
- **Driver Action:**
  1. First query:
     ```
     Top 5 programming languages in 2024
     ```
     *(Initial miss, gets stored).*
  2. Second query:
     ```
     Top 10 programming languages in 2024
     ```
- **Driver Highlights:**
  - Without our verifier, raw cosine similarity between "Top 5" and "Top 10" is **0.978**!
  - But CacheIQ's **Match Verifier (Rule V5)** catches the number discrepancy:
    - Outcome: **MISS** (`MISS_NUMERIC_MISMATCH`).
    - Inspector reason: *"Numbers differ: query has {10}, candidate has {5}."*
  - Next, query a temporal request:
    ```
    What is the latest Python version?
    ```
  - Outcome: **MISS** (`MISS_TIME_SENSITIVE`). Temporal queries bypass the cache in both directions to prevent stale data.

---

### Step 4: The Strategy Arena & Threshold Sweep [1:10 – 1:40] (30 seconds)
- **Speaker:** "How do we prove this works? We built the **Cache Arena** to evaluate 4 strategies side-by-side against our 120 human-labeled eval dataset."
- **Driver Action:**
  1. Navigate to the **Arena** tab (`/arena.html`).
  2. Click **Run Benchmark** (or inspect latest run table).
- **Driver Highlights:**
  - Point to the 4 strategies:
    1. **No Cache:** 0% hit rate, zero LLM calls saved.
    2. **Exact Match (SHA-256):** 9% hit rate, 100% precision, but misses 90%+ of rephrasings.
    3. **Semantic Raw (Bare Threshold):** 37% hit rate, but suffers a **38% false-hit rate (wrong answers)**!
    4. **Semantic Verified (CacheIQ):** Eliminates wrong answers with **100% precision (0% false hits)** while capturing semantic rephrasings.
  - Point out the **Threshold Sweep Curve** below the table, showing the trade-off curve between precision and recall across thresholds (0.70 to 0.95).

---

### Step 5: System Telemetry & Cost Savings [1:40 – 2:00] (20 seconds)
- **Speaker:** "All savings and latencies are backed by measured numbers, never vanity estimates."
- **Driver Action:**
  1. Navigate to the **Analytics** tab (`/analytics.html`).
- **Driver Highlights:**
  - Show the 8 real-time telemetry cards: Total Queries, Cache Hits, Cache Misses, Hit Rate, LLM Calls Avoided, LLM Calls Made, Average Hit Latency (pgvector HNSW) vs. Average Miss Latency.
  - Reason-Code breakdown showing exact frequency of `HIT_SEMANTIC`, `HIT_EXACT`, `MISS_NUMERIC_MISMATCH`, and `MISS_TIME_SENSITIVE`.
  - Conclude: *"CacheIQ delivers fast, explainable, and provably safe semantic caching for LLM applications."*

---

### Fallback Plan (Contingency)
- If network or local Docker services are unavailable:
  1. Use pre-rendered static screenshots from `docs/` and `data/results/sweep.png`.
  2. Run the mock mode backend (`MOCK_API=1 uvicorn backend.app.main:app`) which guarantees deterministic responses without database or network dependencies.

