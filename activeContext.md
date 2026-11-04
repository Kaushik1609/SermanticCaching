# Active Context — CacheIQ

## System State
- **Project:** CacheIQ — Explainable Semantic Cache for LLM Apps
- **Source of Truth:** `docs/00_MAIN_PRD.md`
- **Current Phase:** All Builder 1 (P0 to P7) and Builder 2 (B2-1 to B2-12) phases completed; system is ready for live demo and evaluation
- **Role:** Builder 2 (Evaluation Dataset, Frontend Modularization, Documentation, QA)

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
9. **Modular Frontend JS:** Clean separation into `frontend/js/api.js`, `chat.js`, `analytics.js`, `entries.js`, and `arena.js`.

## Builder 2 Deliverables Complete
- **Evaluation Dataset:** 120 human-reviewed pairs in `data/eval/pairs.jsonl` validated by `backend/tests/test_dataset.py`.
- **Frontend Pages:** All 4 screens (`index.html`, `analytics.html`, `entries.html`, `arena.html`) wired to modular JS and matching the PRD §9 DOM ID Contract.
- **Documentation:** `README.md`, `docs/demo_script.md` (2-minute script), `docs/dataset_notes.md`, `docs/bugs.md` (12-flow QA pass), and `docs/builder2.md`.

