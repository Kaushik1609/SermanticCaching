# Active Context — CacheIQ

## System State
- **Project:** CacheIQ — Explainable Semantic Cache for LLM Apps
- **Source of Truth:** `docs/00_MAIN_PRD.md`
- **Current Phase:** All Builder 1 phases (P0 to P7) completed; ready for Builder 2 (Frontend wiring & UI integration)
- **Role:** Builder 1 (Backend, Algorithms, Evaluation)

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
8. **Evaluation Proof:** The sweep proves that without the Match Verifier, `semantic_raw` suffers from a 38% false-hit rate at threshold 0.85, whereas `semantic_verified` eliminates wrong answers (0% false-hit rate, 100% precision).

## System Deliverables Ready for Builder 2
- **Mock & Real APIs:** All endpoints in PRD §7 implemented (`/api/query`, `/api/stats`, `/api/entries`, `/api/arena/*`, `/api/health`, `/api/config`).
- **UI Design:** Raw Stitch export in `frontend/design/` ready to be wired to the DOM ID contract.
- **Evaluation Assets:** `data/results/sweep.png`, `data/results/arena.json`, and `data/results/latency.json` ready for presentation.

