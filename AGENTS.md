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

### 2026-10-13 — Optimize Docker image size from ~3.2GB to ~900MB

**Problem:** The Docker image for velonote was ~3.2GB uncompressed (888MB download). The bulk was due to:
1. PyTorch CPU, Transformers, SciPy, Scikit-Learn, and SymPy being installed solely to generate embeddings with `all-MiniLM-L6-v2`.
2. PyTorch wheel including ~70MB of C++ development headers (`torch/include`) and unstripped `.so` binaries.
3. Debian `ffmpeg` package pulling full video codec chains, Mesa, and X11 graphics libraries.
4. `libxrender-dev` installing dev headers instead of `libxrender1`.
5. `.dockerignore` missing `backups/`, causing local database dumps to be baked into the image.
6. `COPY . .` followed by `RUN chown -R` in a separate layer duplicating overlayfs metadata.

**Fix:**
- Replaced `torch`, `sentence-transformers`, `scipy`, and `scikit-learn` with `fastembed` (ONNX Runtime) in `requirements.txt`.
- Built `FastEmbedModelWrapper` in `app/processing/embeddings.py` and `app/processing/search.py` producing 100% vector-identical embeddings (`cosine_similarity = 0.9999999`) with graceful fallback.
- Streamlined `Dockerfile`: removed custom PyTorch wheel scraping, added binary `.so` stripping (`strip --strip-unneeded`), pruned package test suites and `__pycache__`, uninstalled `pip/setuptools/wheel` from runtime venv.
- Replaced `libxrender-dev` with `libxrender1`, added dpkg doc exclusion rules, and pruned apt caches.
- Updated `.dockerignore` to ignore `backups/`, test scripts, and dev configs.
- Created `appuser` before copying and applied `--chown=appuser:appgroup` directly on `COPY . .`.
- Accelerated CI build pipeline (`.github/workflows/docker.yml`): parallelized backend and frontend image builds across concurrent runners, removed redundant QEMU emulation overhead, added scoped GHA build caches (`scope=backend` and `scope=nginx`) to prevent cache eviction, and enabled BuildKit npm/apt cache mounts.

### 2026-10-13 — Fix Dockerfile.nginx build failure caused by global .dockerignore

**Problem:** GitHub Actions CI job `build-nginx` failed with `CopyIgnoredFile: Attempting to Copy file "frontend" that is excluded by .dockerignore` and `"/frontend": not found`. The previous optimization commit added `frontend/` to the global `.dockerignore`, which blocked `app/Dockerfile.nginx` from accessing `frontend/` source code during its multi-stage build.

**Fix:**
- Removed `frontend/` from global `.dockerignore`, keeping build artifacts and dependency exclusions (`node_modules/`, `dist/`, etc.).
- Created `Dockerfile.dockerignore` specifically for backend `Dockerfile` builds so the backend image continues to exclude `frontend/` without breaking `Dockerfile.nginx`.

### 2026-10-14 — Remove duplicate DB_PASSWORD from secrets.env & make secrets.env optional in Docker Compose

**Problem:** `DB_PASSWORD` was duplicated across both `.env` and `secrets.env`. Furthermore, `docker-compose.yml` and `docker-compose.dev.yml` hard-required `secrets.env` under `env_file`, preventing users from starting Docker Compose cleanly on a fresh clone where `secrets.env` had not yet been generated.

**Fix:**
- Removed `DB_PASSWORD` from `secrets.env.example`, the active `secrets.env`, and removed its automatic generation in `app/config.py` `_generate_secrets()`. Database connection credentials now reside exclusively in `.env`.
- Changed `secrets.env` in `docker-compose.yml` and `docker-compose.dev.yml` to use `path: secrets.env, required: false`. Docker Compose will no longer fail if `secrets.env` is absent on boot.
- Updated `.github/workflows/docker.yml` to validate compose configurations without requiring a stub `secrets.env`.

### 2026-10-14 — Fix PermissionError on /app/config/app.config.json in Docker containers

**Problem:** Worker or API containers crashed on boot with `PermissionError: [Errno 13] Permission denied: '/app/config/app.config.json'`. This occurred because `./config` was mounted as a volume owned by host/root, but `docker-entrypoint.sh` only adjusted permissions for `/app/data` and `/app/logs`, leaving `/app/config` and `/app/backups` un-chowned. When `appuser` (UID 568) tried to create `app.config.json` via `_ensure_config_file()`, the OS denied write permissions.

**Fix:**
- Updated `docker-entrypoint.sh` to include `/app/config` and `/app/backups` in `mkdir -p`, `chown -R`, and `chmod -R u+rwX`.
- Updated `Dockerfile` to create `/app/config` during the image build step.
- Wrapped `_ensure_config_file()` and `_generate_secrets()` in `app/config.py` with defensive `try-except` blocks to fall back to defaults rather than crashing the container if file writing fails.

### 2026-10-14 — Rename image tags to backend and frontend

**Problem:** Image tagging in GHCR and `docker-compose.yml` was asymmetric: backend was tagged `:latest` / `:<sha>` while frontend was tagged `:nginx-latest` / `:nginx-<sha>`, reflecting server technology rather than component role.

**Fix:**
- Updated `.github/workflows/docker.yml` to tag the backend image as `:backend-latest` and `:backend-<sha>` (retaining `:latest` and `:<sha>` for backwards compatibility), and the frontend image as `:frontend-latest` and `:frontend-<sha>` (retaining `:nginx-latest` as legacy fallback).
- Updated `docker-compose.yml` to use `ghcr.io/kahmeng15/velonote:backend-latest` for `api` & `worker`, renamed service `nginx` to `frontend`, and tagged it with `ghcr.io/kahmeng15/velonote:frontend-latest`.

### 2026-10-14 — Fix NumPy/OpenBLAS ELF load command alignment crash caused by strip

**Problem:** `velonote_worker` and `velonote_api` crashed on startup with `ImportError: libscipy_openblas64_-32a4b2a6.so: ELF load command address/offset not page-aligned` when importing NumPy/cv2. This happened because `strip --strip-unneeded` in `Dockerfile` was executed over all `.so` files in `/opt/venv`, which modified the precompiled ELF headers of vendored OpenBLAS binaries from PyPI wheels, violating Linux page-alignment constraints.

**Fix:**
- Removed `strip --strip-unneeded` from `Dockerfile`. Precompiled wheels on PyPI are already stripped and must not be re-stripped.

### 2026-10-14 — Relocate secrets.env to config/ directory

**Problem:** `secrets.env` was placed in the project root, which is not mounted as a volume in production Docker Compose (`./config:/app/config` is mounted). This prevented auto-generated secrets from persisting to the host and being automatically shared between `api` and `worker` containers.

**Fix:**
- Relocated `secrets.env` and `secrets.env.example` to `config/secrets.env` and `config/secrets.env.example`.
- Updated `app/config.py` to auto-generate and prioritize `config/secrets.env`, while preserving backward-compatible fallback to root `secrets.env`.
- Updated `docker-compose.yml` and `docker-compose.dev.yml` to optionally load `config/secrets.env`.

### 2026-10-14 — Streamline Docker Compose: local bind mounts, env_file simplification, and init_db retry

**Problem:**
1. Postgres (`pgdata:`) and Ollama (`ollama_models:`) used Docker-managed named volumes instead of local directory folders in the deployment directory.
2. `docker-compose.yml` had redundant `env_file` paths for `secrets.env`, which Python (`app/config.py` via Pydantic) already auto-discovers directly from `/app/config/secrets.env`.
3. Startup depended on `condition: service_healthy` on `db`, delaying container starts and failing if healthchecks drifted.
4. `extra_hosts` added unnecessary host-gateway resolution for purely containerized deployments.

**Fix:**
- Switched Postgres and Ollama volumes to local bind mounts (`./pgdata:/var/lib/postgresql/data` and `./ollama_models:/root/.ollama`), eliminating top-level named volumes.
- Added `pgdata/` and `ollama_models/` to `.gitignore`, `.dockerignore`, and `Dockerfile.dockerignore`.
- Simplified `env_file` to only `- .env` in `docker-compose.yml` and `docker-compose.dev.yml`.
- Added resilient connection retry loop (15 attempts with 2s interval) in `init_db()` in `app/utils/db.py`, allowing containers to boot cleanly without `condition: service_healthy`.
- Removed `extra_hosts` host-gateway mappings.

### 2026-10-15 — Human-readable PostgreSQL error diagnostics and dynamic external DB support

**Problem:** When connecting to an external PostgreSQL database (outside the Docker stack), database errors were opaque and hard to debug. In addition, `worker` had `DB_HOST=db` hardcoded under `environment:` in `docker-compose.yml`, which overrode `.env` and broke external DB setups.

**Fix:**
- Added `diagnose_db_error(exc)` in `app/utils/db.py` to parse raw PostgreSQL/psycopg2 errors and output actionable messages:
  - Authentication failure: states user and points to `DB_USER` / `DB_PASSWORD`.
  - Database not found: identifies the missing database and suggests `CREATE DATABASE`.
  - Table not found: identifies the specific missing table.
  - DNS resolution failure: explains hostname resolution failure inside Docker.
  - Connection refused: explains server state and alerts about `localhost` inside Docker containers.
  - Network timeout / unreachable: points to firewall/security group blocks.
- Integrated `diagnose_db_error()` into `init_db()`, worker task processing & polling loops, and the `/health` API endpoint.
- Initialized logging in `app/main.py` (`setup_logging()`) on boot so database connection logs and diagnostics format properly to stdout/console.
- Made `DB_HOST=${DB_HOST:-db}` dynamic in `docker-compose.yml` so `.env` overrides are honored.
