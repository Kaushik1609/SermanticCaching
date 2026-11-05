# Active Context — CacheIQ

## System State
- **Project:** CacheIQ — Explainable Semantic Cache for LLM Apps
- **Source of Truth:** `docs/00_MAIN_PRD.md`
- **Current Phase:** Phase P8 (Traffic Simulation & Zipf Evaluation) completed; system audited and 100% green
- **Role:** Builder 1 (Backend, Algorithms, Evaluation) & Builder 2 (Dataset, UI, Docs)

## Key Architectural Decisions
1. **D1 (UI Serving):** Static HTML + Tailwind CDN + Vanilla JS served via FastAPI `StaticFiles(directory="frontend", html=True)`.
2. **Contract Freeze:** `models.py` and `migrations/001_init.sql` frozen at P0. Any changes require updating `docs/00_MAIN_PRD.md` first.
3. **Database:** Docker Postgres with `pgvector/pgvector:pg16`.
4. **Mock API:** Controlled via `MOCK_API=1` environment variable. Unblocks Builder 2 frontend wiring immediately.
5. **Stitch Design Export:** Raw export located in `frontend/design/`:
   - `cache_console.html`: Full Stitch-generated markup
   - `cache_console_preview.jpg`: Screenshot render
   - `design_system.md`: Full style specification and tokens
6. **Embeddings:** `all-MiniLM-L6-v2` L2-normalised (unit length) vectors; cosine similarity = dot product.
7. **Match Verifier Architecture:** Strict architectural separation: `engine/verifier` imports zero modules from `engine/search` or `engine/store`. Evaluates rules V1..V5 in exact order.
8. **Evaluation Proof:**
   - On the pairs dataset, `semantic_raw` suffers from a 38% false-hit rate at threshold 0.85, whereas `semantic_verified` eliminates wrong answers (0% false-hit rate, 100% precision).
   - In realistic Zipf traffic simulation ($N=1000, \alpha=1.1$ on the test split), `semantic_raw` yields 38 false hits (serving incorrect cached answers), whereas `semantic_verified` reduces false hits by 63% (14 false hits, 98.42% precision) while avoiding 887 LLM calls ($23.15 cost saved assumed, 1330.5s simulated LLM latency saved).
9. **Modular Frontend JS:** Clean separation into `frontend/js/api.js`, `chat.js`, `analytics.js`, `entries.js`, and `arena.js`.
10. **Traffic Simulation & Split Integrity:** `scripts/traffic_sim.py` generates workloads strictly using the TEST split, constructs multi-variant intents for "same" pairs, and enforces complete isolation using transient context keys.

## Test & Build Status
- **Pytest:** 65 passed, 0 skipped (`pytest backend/tests -v`).
- **Target:** `make traffic` runs `python scripts/traffic_sim.py` seamlessly.
- **Results:** `data/results/traffic.json` and `data/results/traffic.png` updated and verified.
