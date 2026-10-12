# velonote — Agent Instructions

## Architecture

**Monolithic FastAPI app + dedicated background worker + React frontend (Vite + Mantine).** No Celery/Redis Queue — tasks are DB-backed (`Task` table polled by `worker_main.py`). Backend is API-only (no HTML/static served).

- `app/main.py` — API entrypoint, registers routers, lifespan (init DB, bootstrap admin/templates), CORS/CSRF/rate-limit/security-headers middleware
- `app/worker_main.py` — polls `Task` table; handlers in `TASK_REGISTRY` dict (`app/worker_main.py:21`)
- `app/models/db.py` — all SQLAlchemy ORM models (~580 lines)
- `app/schemas/` — Pydantic models (`schemas.py`, `admin.py`, `analytics.py`, `exercise.py`)
- `app/processing/` — document extraction (`smart_pipeline.py`, `unified_processor.py`), image extraction (`image_extractor_v2.py`, `image_text_mapper.py`), scanned doc OCR (`scanned_doc_handler.py`, `image_preprocessor.py`), AI client, embeddings
- `app/utils/` — auth (JWT), db session, tasks (DB-backed queue), websocket, caching
- `frontend/` — React app (Vite). Dev server proxies `/api` → `localhost:8000` (`frontend/vite.config.js`)

## Key commands

```bash
brew install tesseract poppler                              # System deps (macOS)
pip install -r requirements.txt
./scripts/dev.sh                                             # API + Worker + Frontend (parallel, local)
./scripts/dev.sh --docker                                    # Or: docker compose -f docker-compose.dev.yml up (dev containers with file watchers)
docker compose -f docker-compose.dev.yml --profile builtin up # Dev containers with local Ollama
python -m uvicorn app.main:app --reload                      # API only
python -m app.worker_main                                    # Worker only
cd frontend && npm run dev                                   # Frontend only
docker compose up -d --build                                 # Full prod stack
docker compose -f docker-compose.dev.yml up -d db            # Infra only for local dev
cd frontend && npm run lint                                  # Frontend lint
python scripts/resource_processing_test/process_all.py        # One-command: drop file in input/, run this
python scripts/resource_processing_test/run_test.py           # Offline extraction test (all formats + images)
python scripts/resource_processing_test/run_test.py --historical  # With quality trend tracking
python scripts/resource_processing_test/correction_tool.py "output/reports/OUTPUT_lecture.md"  # Interactive correction
python scripts/resource_processing_test/analyze_corrections.py --suggest-tweaks  # Pipeline improvement suggestions
python scripts/run_benchmark.sh                             # Full benchmark suite
```

No Python tests exist — no `test_*.py` files in the repo. Use the test harness in `scripts/resource_processing_test/` instead.

## Database

PostgreSQL. `DATABASE_URL` auto-constructed from `DB_USER/PASSWORD/HOST/PORT/NAME` env vars (`app/config.py:164`). **Do not set `DATABASE_URL` directly.** No migration tool — tables auto-created via `Base.metadata.create_all()` in `init_db()`. Add schema changes as programmatic one-off migrations in `app/utils/db.py` (see `apply_postgresql_migrations()`, etc.).

## Background tasks

Submit tasks via `TaskManager.submit_task(task_id, task_type, user_id, **kwargs)`. Worker polls for `status="pending"` tasks with per-user concurrency limits (`RateLimitConfig`). WebSocket pushes progress to `ConnectionManager` keyed by user_id.

## AI client (`app/processing/ai_client.py`)

3-tier fallback (Gemini → Gemini → Ollama). Resolution: user personal settings > global settings (`GLOBAL_AI_TIER*` env vars) > legacy fallbacks (`GEMINI_API_KEY`, etc.). Gemini model dynamically selected at init; falls back to `gemini-1.5-flash`.

## Router conventions

Every endpoint takes `current_user: User = Depends(get_current_user)` and `db: Session = Depends(get_db)`. Always filter queries by `user_id`. Use `response_model=` with schemas from `app/schemas/`.

## Settings & Auth

- `get_settings()` via `app/config.py` (lru_cache) — never instantiate `Settings()` directly.
- JWT: `Authorization: Bearer <token>` header or `access_token` cookie.
- CSRF enforced for cookie-authenticated sessions. Exempt paths listed in `app/main.py:254-261`.
- Sliding session re-issues tokens on activity (`X-New-Token` response header).
- Rate limiting: per-endpoint burst limits defined in `_RATE_LIMIT_POLICY` dict (`app/main.py:150-156`).

## Production safety

Startup blocks if: `SECRET_KEY < 32 chars`, `DATABASE_URL` not PostgreSQL, or CORS has wildcard origin. Set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `APP_ENCRYPTION_KEY`.

## Key patterns

- **File storage:** `uploads/{user_id}/{lecture_id}/`, `generated/{lecture_id}/`, `data/extracted_images/{resource_id}/` (extracted diagrams/images), `data/resources/{resource_id}/` (text + structured JSON + images metadata)
- **ID generation:** prefixed hex IDs (`gp_`, `sj_`, `rs_`, `nt_`, `ex_`, `mg_`, `cv_`) via `generate_random_id()` in `app/utils/db.py`
- **Pipeline singleton:** `app/routers/processing.py → _pipeline` (module-level, reused across requests)
- **Unified processing:** `app/processing/unified_processor.py` → `UnifiedContentProcessor.extract()` is the single entry point for all formats. Used by both `process_resource_task` and `process_exercise_task`. Returns `ContentBundle { markdown, images[], image_map, processing_path, timings, warnings }`.
- **Image extraction:** `ImageExtractorV2` in `image_extractor_v2.py` handles all formats (PDF/PyMuPDF+OpenCV, PPTX/python-pptx shapes, DOCX/python-docx inline, image files). `ImageClassifier` filters logos/backgrounds/decorations. `ImageTextMapper` places images inline near their corresponding text by position.
- **Scanned doc detection:** `ScannedDocHandler` checks text density (<50 chars/page = scanned). Routes to Tesseract with PSM configuration based on document type (printed/handwritten/mixed). `ImagePreprocessor` applies deskew, CLAHE, denoise, binarize before OCR.
- **Startup bootstrap:** Admin user from `ADMIN_EMAIL` env var, `SystemSettings` row, export template seeding — all in `main.py` lifespan
- **Migrations:** Add to `app/utils/db.py` as new `apply_*_migration()` functions called from `init_db()` — never hand-write SQL migration scripts

### 2026-06-29 — Comprehensive processing overhaul: unified pipeline, image extraction, OCR, test harness

**What was built:**

1. **`UnifiedContentProcessor`** (`app/processing/unified_processor.py`) — single entry point for ALL formats. Auto-detects scanned PDFs vs native. Returns `ContentBundle { markdown, images[], image_map, ... }`.

2. **`ImageExtractorV2`** (`app/processing/image_extractor_v2.py`) — extracts images from PDF (PyMuPDF + OpenCV), PPTX (python-pptx shapes), DOCX (inline), and image files. `ImageClassifier` filters logos, backgrounds, decorations using size/position/repetition/variance heuristics.

3. **`ImageTextMapper`** (`app/processing/image_text_mapper.py`) — places images inline near their corresponding text by slide/page position. Detects "as shown in the figure" references.

4. **`ScannedDocHandler`** (`app/processing/scanned_doc_handler.py`) — detects scanned PDFs via text density (<50 chars/page). Routes to Tesseract with per-document-type PSM config (printed/handwritten/mixed).

5. **`ImagePreprocessor`** (`app/processing/image_preprocessor.py`) — deskew, CLAHE contrast enhancement, denoise, perspective correction, binarization for OCR.

6. **DOCX support** added to `SmartPipeline._process_docx()` — style-based heading detection, list detection.

7. **`process_resource_task`** and **`process_exercise_task`** both use `UnifiedContentProcessor` now.

8. **Test harness** (`scripts/resource_processing_test/`) — comprehensive `run_test.py` with structural diff engine, quality metrics (overall_score, structural_validity, content_preservation, consistency, image_recall), report generation, and historical trend tracking.

9. **Correction CLI** (`correction_tool.py`) — interactive tool for marking heading/list/image/OCR corrections.

10. **Self-improvement engine** (`analyze_corrections.py`) — pattern analysis across accumulated corrections, suggests pipeline parameter tweaks.

11. **Image serving API** (`GET /resources/{id}/images/{path}`).

12. **Automation**: `scripts/run_benchmark.sh`, `.githooks/pre-commit`.

**All local.** No external API calls required. Tesseract for OCR, python-pptx/PyMuPDF/python-docx for extraction, OpenCV for image processing. Ollama as optional AI polish.

## Session Log

### 2026-06-26 — Fix infinite API refetch loop in ExerciseView TaskContext watcher

**Problem:** When reprocessing an exercise, `ExerciseView.jsx` spammed `GET /exercises/{id}` in an infinite loop. The TaskContext watcher had `[tasks, exercise, id]` as deps — every poll cycle (3s) where a **completed** task matched the exercise, it called `fetchApi()` → `setExercise(data)` (new object ref) → `exercise` changed → effect re-ran → refetch → infinite loop.

**Fix:** Added `prevExerciseTaskStatus` ref (`ExerciseView.jsx:124`) to track the last known task status. The refetch on completion now only fires on transition from an active status (pending/processing/running) → `completed`, not when the task is already `completed`. At `ExerciseView.jsx:172`.

### 2026-06-26 — Fix event propagation in SubjectView resource 3-dot menu

**Problem:** In the Resource tab of `SubjectView.jsx`, clicking menu items (Reprocess, Rename, Cancel Processing, Delete) in the `Menu.Dropdown` triggered the note card's `onClick` handler, navigating to the resource instead of opening the confirmation modal. The `Menu.Item` handlers were missing `e.stopPropagation()`.

**Fix:** Added `e.stopPropagation()` to all four `Menu.Item` click handlers in the note card's dropdown menu (`SubjectView.jsx:1288-1308`).

### 2026-06-26 — Remove filename from NoteView sticky header

**Problem:** `NoteView.jsx` displayed `note.title` (the filename) as a large bold text below the breadcrumb row in the sticky header, making it redundant and visually noisy.

**Fix:** Removed the title rendering block from the sticky header (`NoteView.jsx:565-569`).

### 2026-06-26 — Align ExerciseView processing screen with NoteView

**Problem:** The ExerciseView processing screen used a `Card` with `Loader` and different styling, unlike NoteView's centered `IconRobot` + progress layout.

**Fix:** Replaced ExerciseView's `taskActive` and `taskFailed` blocks (`ExerciseView.jsx:536-561`) to match NoteView's exact layout: `Box mt={100} ta="center"`, `IconRobot` (active) / `IconAlertCircle` (failed), same title/text/progress styling. Added `IconRobot`/`IconAlertCircle` to imports.

### 2026-06-26 — Hide sidebar during processing in ExerciseView

**Problem:** The right sidebar (exercise info, smart actions, export) was visible during processing, cluttering the view.

**Fix:** Wrapped the sidebar `Box` in `{!taskActive && (...)}` (`ExerciseView.jsx:931-1111`) to hide it while a task is active.

### 2026-10-07 — Remove Redis and integrate DB backup management in Worker and Admin UI

**Problem:** Too many redundant containers (`db-backup`, `redis`). Database backups lacked admin UI controls to trigger, list, download, or delete snapshots.

**Fix:**
- Removed Redis container and dependencies completely, replacing it with a thread-safe `InMemoryTTLCache` in `app/utils/cache.py`.
- Consolidated daily automated database backups into `app/worker_main.py` via `app/utils/backup.py`.
- Added backup management endpoints in `app/routers/admin.py` (`GET /admin/backups`, `POST /admin/backups/create`, `GET /admin/backups/{filename}/download`, `DELETE /admin/backups/{filename}`).
- Integrated interactive backup management in `Admin.jsx` with a snapshots table, instant backup creation, download, delete, and retention schedule controls.

