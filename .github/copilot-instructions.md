# velonote – Copilot Instructions

## Architecture Overview

**Monolithic FastAPI app** (no microservices). Single SQLite database (`data/app.db`), no Redis/Celery. Background jobs run in a `ThreadPoolExecutor` with in-memory tracking (`app/utils/tasks.py → tasks_tracking` dict).

**Data hierarchy:** `User → SubjectGroup → Subject → Lecture → GeneratedDocument / Flashcard / ChatMessage / LectureEmbedding`

**Key directories:**
- `app/routers/` – One router file per feature; all registered in `main.py` via `app.include_router()`
- `app/models/db.py` – All SQLAlchemy ORM models (single file, 227 lines)
- `app/schemas/schemas.py` – All Pydantic request/response models (single file)
- `app/processing/` – Document extraction pipeline, AI client, embeddings, and text processors
- `app/utils/` – Shared utilities: `auth.py` (JWT), `db.py` (session mgmt), `tasks.py` (background jobs), `websocket.py` (real-time)
- `app/static/` – Vanilla HTML/CSS/JS frontend (no build step)
- `uploads/{user_id}/` – Raw uploaded files; `generated/{lecture_id}/` – AI-produced files; `output/images/` – extracted images

## Developer Workflow

```bash
# Setup (macOS)
brew install tesseract poppler   # Required system deps for OCR, PDF rendering

# Python environment
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Environment config
cp .env.example .env && vim .env  # Set GEMINI_API_KEY or HUGGINGFACE_TOKEN

# Run server
python main.py                    # Starts on http://localhost:8000

# Interactive API docs
http://localhost:8000/docs        # Swagger UI for testing all endpoints

# Run tests
pytest tests/ -v

# Manually test extraction pipeline (no server needed)
python ProcessingAlgorithmTest/run_smart.py
```

**Database:** Tables auto-created on startup via `Base.metadata.create_all()` in `app/utils/db.init_db()`. No migration tool needed—schema evolved in-place.

**Lifespan pattern** (`main.py`):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init_db() runs here
    init_db()
    yield
    # Shutdown: cleanup happens here
```

## Coding Patterns

### Router conventions
Every endpoint takes `current_user: User = Depends(get_current_user)` and `db: Session = Depends(get_db)`. Always filter DB queries by `user_id` for ownership/security:
```python
# app/routers/lectures.py
@router.get("")
async def get_lectures(
    subject_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Lecture).filter(Lecture.user_id == current_user.id)
    if subject_id:
        query = query.filter(Lecture.subject_id == subject_id)
    return query.order_by(Lecture.created_at.desc()).all()
```

### Response models
All endpoints return Pydantic models from `app/schemas/schemas.py`. Use `response_model=` parameter:
```python
@router.get("", response_model=List[LectureResponse])
```

### Auth
JWT token is passed as `Authorization: Bearer <token>` header (NOT a cookie). Auth dependency in `app/utils/auth.py → get_current_user()` extracts and validates token.

### AI client
`AIClient(user=current_user)` in `app/processing/ai_client.py` resolves provider/key in priority order:
1. **User personal settings** — `user.ai_provider`, `user.ai_api_key`, etc. (most specific)
2. **Global settings** — `GLOBAL_AI_*` env vars when `user.use_global_ai_config=True`
3. **System fallback** — `AI_PROVIDER`, `GEMINI_API_KEY` env vars (least specific)

Gemini model is **dynamically selected** at init by listing available models; falls back to `gemini-1.5-flash`.

### Document processing pipeline
`SmartPipeline` (`app/processing/smart_pipeline.py`) runs three stages on PDF/PPTX:
1. **Table extraction** (pdfplumber) — detect & convert tables to markdown
2. **Font-aware text extraction** (`FontAwareExtractor`) — main extraction pass preserving document structure
3. **Layout detection** (YOLO-DocLayNet, optional) — disabled by default in production

The pipeline is **module-level singleton** in `app/routers/processing.py → _pipeline`, reused across requests. Configuration:
```python
pipeline = SmartPipeline(
    use_layout_detection=False,   # Enable when YOLO model downloaded
    use_table_transformer=False,  # Enable when Table Transformer downloaded
)
markdown = pipeline.process(file_path)  # Returns clean markdown string
```

### Embeddings & Vector Database

**Vector DB Approach:** Pre-computed embeddings stored in SQLite (not external service).

**Schema:**
- `LectureEmbedding` table: stores chunks + embeddings for each lecture
  - `lecture_id`, `chunk_text`, `chunk_index`, `embedding` (JSON), `position`, `created_at`
  
**Lifecycle:**
1. **Upload/Reprocess:** When `extracted_text` is set, call `compute_and_store_embeddings(lecture_id, text, db)`
   - Chunks text (500 chars each) → computes embeddings → stores in DB
2. **Edit Note:** PUT `/lectures/{id}/content` auto-calls `update_lecture_embeddings()` 
   - Deletes old embeddings + recomputes new ones
3. **Chat Query:** `retrieve_relevant_chunks(query, lecture_ids, db, top_k=3)` 
   - Retrieves pre-computed embeddings from DB
   - Computes query embedding once
   - Performs cosine similarity search (fast!)

**Key Functions in `app/processing/embeddings.py`:**
- `compute_and_store_embeddings(lecture_id, text, db)` – compute & store
- `update_lecture_embeddings(lecture_id, text, db)` – delete old + recompute
- `retrieve_relevant_chunks(query, lecture_ids, db, top_k)` – vector search

**Chat Integration:**
- `POST /chat/ask` in `app/routers/chat.py` uses `retrieve_relevant_chunks()`
- No re-computing embeddings on every query
- Faster retrieval for large knowledge bases (10+ lectures per group)

**Migration:**
- Run `python scripts/migrate_embeddings.py` once to backfill embeddings for existing lectures

### WebSocket
`app/utils/websocket.py → manager` is a global `ConnectionManager` keyed by `user_id`. Use `await manager.broadcast_to_user(user_id, {...})` to push progress events to the frontend. Useful for real-time extraction/processing status updates during long-running operations.

### Settings
All config comes from `.env` via `pydantic_settings` (`app/config.py → get_settings()`). The instance is `@lru_cache`-decorated — call `get_settings()` at module level or inside functions; never instantiate `Settings()` directly.

### Background Tasks & Job Tracking
Use `TaskManager.submit_task()` in `app/utils/tasks.py` to run long-running operations in the thread pool:
```python
# In a router endpoint (async context)
task_id = str(uuid.uuid4())
TaskManager.submit_task(task_id, expensive_function, arg1, arg2, kwarg=value)

# Check status via /tasks/{task_id}
# Status tracked in-memory via tasks_tracking dict
# Production: migrate to database for persistence across restarts
```

### File Storage Patterns
- **Uploads:** `uploads/{user_id}/{lecture_id}/`, raw user files
- **Generated:** `generated/{lecture_id}/`, AI-produced content (PDFs, markdown files)
- **Output:** `output/images/{lecture_id}/`, extracted images from documents
- **Database:** Paths stored in `Lecture.file_path` and `Lecture.output_pdf_path`

### Frontend JavaScript Patterns
Frontend is vanilla JS in `app/static/` (no build step, no framework dependencies):
- `auth.js` — JWT token mgmt (`localStorage.getItem('token')`), HTTP header injection
- `nav.js` — Navigation and layout helpers, modal/dialog utilities
- `utils.js` — Shared fetch utilities with auth headers, error handling
- `greetings.js` — Personalized greeting generator
- All pages are dynamic HTML served from specific routes in `main.py`; populate via fetch calls to API endpoints
- Response models from API are consumed directly in JavaScript (Pydantic models → JSON)

### Error Handling
- Use `HTTPException` with appropriate status codes in routers
- Always check auth: `current_user` from `get_current_user()` dependency
- Always validate ownership: filter queries by `user_id`
- Return meaningful error messages in detail field

## External Dependencies

| Dep | Purpose | Notes |
|-----|---------|-------|
| `tesseract` + `pytesseract` | OCR for image slides | System binary required |
| `poppler` + `pdf2image` | PDF → image rendering | System binary required |
| `google-generativeai` | Gemini LLM | Needs `GEMINI_API_KEY` |
| `huggingface_hub` | HF Inference API | Needs `HUGGINGFACE_TOKEN` |
| `sentence-transformers` | Local CPU embeddings | Auto-downloads model on first run |
| `pdfplumber` | PDF text/table extraction | Pure Python, no system dep |
| `python-pptx` | PPTX parsing | Pure Python |

## Ollama (Local LLM)

To use a self-hosted LLM instead of Gemini/HuggingFace, point the app at a running Ollama instance:

```env
OLLAMA_BASE_URL=http://localhost:11434   # or remote host
AI_PROVIDER=ollama
```

Per-user override: set `user.ai_provider="ollama"` and `user.ai_base_url` in the DB (via the settings page). The `AIClient` will route requests to the Ollama REST API at `{OLLAMA_BASE_URL}/api/generate`. No API key is required.
