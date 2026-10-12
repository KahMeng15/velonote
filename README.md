# velonote – AI-Powered Study Companion

A scalable, AI-powered study companion that intelligently converts lecture slides (PDF/PPTX) into structured study materials. Featuring a **Multi-Container Architecture**, it extracts clean markdown with properly formatted tables, provides RAG-based chat, generates quizzes, and organizes your learning journey. Perfect for personal use or small study groups.

## ✨ Key Features

* **Unified Content Processor**: Single entry point (`UnifiedContentProcessor`) for all document types (PDF, PPTX, DOCX, images). Auto‑detects scanned PDFs and routes to appropriate OCR pipelines.
* **Enhanced Image Extraction (ImageExtractorV2)**: Extracts images from PDF (PyMuPDF + OpenCV), PPTX (python‑pptx shapes), DOCX (inline), and image files. Includes `ImageClassifier` to filter logos, backgrounds, and decorations.
* **Intelligent Image‑Text Mapping**: `ImageTextMapper` places extracted images inline near corresponding text, handling references like “as shown in the figure”.
* **Scanned Document Detection & OCR**: `ScannedDocHandler` detects low‑text‑density PDFs and routes them to Tesseract with optimized PSM settings for printed, handwritten, or mixed content.
* **Image Pre‑processing**: `ImagePreprocessor` applies deskew, CLAHE contrast enhancement, denoising, and binarization before OCR for higher accuracy.
* **Comprehensive Test Harness**: `scripts/resource_processing_test/` provides end‑to‑end validation, structural diff, quality metrics, and historical trend tracking.
* **Interactive Correction CLI**: `correction_tool.py` lets users correct headings, lists, images, and OCR errors interactively.
* **Self‑Improvement Engine**: `analyze_corrections.py` analyses accumulated corrections and suggests pipeline parameter tweaks.
* **UI Enhancements**: Updated ExerciseView processing screen to match NoteView, hidden sidebars during processing, and fixed infinite refetch loop.
* **Robust AI Client**: 3‑tier fallback (Gemini → Gemini → Ollama) with dynamic model selection and reasoning level handling.
* **Semantic Q&A Chat**: Ask questions about your notes with RAG (Retrieval Augmented Generation)
  - Pre-computed embeddings for fast semantic search
  - Vector storage integrated into the database
  - Context-aware LLM responses from multiple AI providers
* **Study Tools**: Quiz generation and cheat sheets
  - Auto-generate practice quizzes from lecture notes
  - Export notes as PDF or Word documents
* **Smart Organization**: Subjects grouped by semester/topic with snapshots
* **Learning Analytics**: Monitor your study progress via a dedicated dashboard
* **Flexible AI**: Support for Gemini API, Hugging Face, and Ollama
* **Scalable Infrastructure**: Multi-container stack with dedicated API, Worker, and DB services
* **Real-Time Updates**: WebSocket support for live extraction progress

## 🏗️ Architecture

velonote uses a **Multi-Container Architecture** to ensure reliable background processing and high availability.

**Stack:**
- **Frontend**: React (Vite) + Mantine UI (served via Nginx in production)
- **API**: FastAPI (Request handling & Auth)
- **Worker**: Python (Background processing: OCR, AI, Embeddings)
- **Database**: PostgreSQL 15 (Persistent storage & Task Queue)
- **Cache**: In-memory TTL cache (Zero-dependency thread-safe caching)
- **Embeddings**: sentence-transformers (Local, CPU-based)
- **Deployment**: Docker Compose

## 🚀 Quick Start (Production / Full Stack)

The easiest way to run the full production stack is using Docker Compose:

### 1. Setup
```bash
# Clone repository
git clone https://github.com/KahMeng15/velonote.git velonote
cd velonote

# Copy environment template and configure
cp .env.example .env
```

#### Configuration (`.env`)
Configure the core options in your `.env` file:
* **Database Configuration**:
  The application automatically constructs the connection string from individual variables. **Do not set a raw `DATABASE_URL` variable**:
  ```env
  DB_USER=velonote
  DB_PASSWORD=velonotepassword
  DB_HOST=localhost # Use 'db' when running inside Docker Compose
  DB_PORT=5432
  DB_NAME=velonote
  ```
* **Ports**:
  ```env
  API_PORT=8000       # FastAPI backend internal port
  FRONTEND_PORT=5173  # Vite React dev server port (development)
  PUBLIC_PORT=3000    # Nginx reverse proxy host port (production)
  ```
* **Two-Category AI Configuration**:
  velonote uses two dedicated AI categories to balance instant interactivity with heavy batch processing accuracy:
  ```env
  # Category 1: Chat / Instant Response (Conversational Q&A, voice, quick grading)
  AI_CHAT_TIER1_PROVIDER=groq
  AI_CHAT_TIER1_MODEL=llama-3.1-8b-instant
  AI_CHAT_TIER1_API_KEY=your_api_key
  AI_CHAT_TIER1_REASONING_LEVEL=low

  AI_CHAT_TIER2_PROVIDER=gemini
  AI_CHAT_TIER2_MODEL=gemini-2.5-flash
  AI_CHAT_TIER2_API_KEY=your_gemini_key

  # Category 2: Document Processing & Heavy Tasks (AI polish, notes, question generation)
  AI_PROCESSING_TIER1_PROVIDER=ollama
  AI_PROCESSING_TIER1_MODEL=qwen2.5:1.5b
  AI_PROCESSING_TIER1_BASE_URL=http://ollama:11434

  AI_PROCESSING_TIER2_PROVIDER=groq
  AI_PROCESSING_TIER2_MODEL=llama-3.3-70b-versatile
  AI_PROCESSING_TIER2_API_KEY=your_api_key

  AI_PROCESSING_TIER3_PROVIDER=gemini
  AI_PROCESSING_TIER3_MODEL=models/gemma-4-26b-a4b-it
  AI_PROCESSING_TIER3_API_KEY=your_gemini_key
  AI_PROCESSING_TIER3_REASONING_LEVEL=high
  ```

### 2. Launch Production Stack
```bash
# Start the full stack with Nginx reverse proxy
docker compose up -d --build
```

**Services:**
- **Web UI**: [http://localhost:3000](http://localhost:3000) (served via Nginx reverse proxy)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Logs**: View via `docker compose logs -f` or in the `./logs` directory.
- **Backups**: Automatic daily PostgreSQL backups managed by worker to `./backups/postgres/`.

---

## 🛠️ Development Setup

velonote supports two development workflows: **Dev Containers with Live File Watchers** (recommended) or **Bare-Metal Local Development**.

### Option A: Dev Containers with File Watchers (Recommended)

Run the entire application stack in isolated containers with full hot-reloading and file watchers. No local Python or Node installation is required!

#### How to Start
```bash
# 1. Start all dev containers (API + Worker + Frontend + DB)
docker compose -f docker-compose.dev.yml up

# Or use the convenience shortcut:
./scripts/dev.sh --docker
```

#### Running with Built-in Local Ollama
To include the local Ollama container (which automatically downloads the lightweight `qwen2.5:1.5b` model on first start):
```bash
docker compose -f docker-compose.dev.yml --profile builtin up
```

#### How the Dev Containers Work
* **Backend API (`velonote_api_dev`)**: Runs `uvicorn` with `--reload` mounted to the project directory. Changes to backend Python files instantly trigger an API reload.
* **Background Worker (`velonote_worker_dev`)**: Monitored by `watchfiles` (`watchfiles 'python -m app.worker_main' app/`). Any edits to extraction pipelines or task handlers automatically restart the worker process. Also executes scheduled database backups.
* **Frontend Dev Server (`velonote_frontend_dev`)**: Runs Vite in dev mode (`npm run dev`) with Hot Module Replacement (HMR) and polling watchers enabled. Edits to React components reflect immediately in the browser.
* **Volume Mounts**: The workspace is live-mounted into the containers. Dependencies are isolated in Docker volumes (`frontend_node_modules`) to keep host and container environments clean.

#### Development Endpoints
* **Frontend UI (Vite HMR)**: [http://localhost:5173](http://localhost:5173)
* **Backend API & Swagger Docs**: [http://localhost:8000](http://localhost:8000) / [http://localhost:8000/docs](http://localhost:8000/docs)
* **PostgreSQL**: `localhost:5432`
* **Local Ollama** (if `--profile builtin` enabled): `http://localhost:11434`

---

### Option B: Bare-Metal Local Development (Host OS)

If you prefer running Python and Node directly on your host machine:

```bash
# 1. Start Database infrastructure only
docker compose -f docker-compose.dev.yml up -d db

# 2. Setup Python virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Install frontend dependencies
cd frontend && npm install && cd ..

# 4. Start all services concurrently (API, Worker, and Frontend)
./scripts/dev.sh
```

---

### Database Backups

A `db-backup` sidecar container runs automatically:

- **Daily**: Runs `pg_dump` once every 24 hours
- **Retention**: Keeps backups for 7 days by default (configurable via Admin Panel → System Settings → `backup_retention_days`)
- **Storage**: Writes to `./backups/postgres/` on the host — inspectable and restorable

**Restore from a backup:**
```bash
docker compose down
docker run --rm -v velonote_pgdata:/var/lib/postgresql/data -v $(pwd)/backups/postgres:/backups alpine sh -c "rm -rf /var/lib/postgresql/data/* && pg_restore -d postgres /backups/backup_20260626_120000.sql"
docker compose up -d
```

**Disable backups** from the Admin Panel, or set `backup_enabled` to `false`.

### PostgreSQL Note

The database uses a **Docker named volume** (`pgdata`) to avoid filesystem permission issues on Linux/TrueNAS. The data is not directly visible on the host, but backups are written to `./backups/postgres/` for easy access.

## 📚 Documentation

- **[Technical Documentation](docs/TECHNICAL_DOCUMENTATION.md)**: Deep dive into the multi-container architecture, data models, and processing pipelines.
- **[Development Guide](docs/DEVELOPMENT.md)**: Detailed instructions for local setup, testing, and contribution.
- **[Resource Requirements](docs/RESOURCE_REQUIREMENTS.md)**: Hardware recommendations for the new architecture.

## 🛠️ Tech Stack Details

| Component | Technology | Purpose |
|-----------|-----------|----------|
| **Reverse Proxy** | Nginx | Serves UI & routes API traffic |
| **Backend API** | FastAPI, Python 3.11+ | Web server & API logic |
| **Worker** | Python (dedicated process) | Background processing (OCR, AI) |
| **Database** | PostgreSQL 15 | Persistent storage & Task Queue |
| **Cache** | In-memory TTL Cache | Thread-safe in-memory response caching |
| **Vector Storage** | PostgreSQL + sentence-transformers | Semantic search |
| **Document Extraction** | pdfplumber, python-pptx | PDF/PPTX parsing |
| **OCR** | Tesseract + pytesseract | Scanned document support |
| **AI/LLM** | Gemini / HF Inference / Ollama | Multiple provider support |
| **Async Tasks** | DB-backed Task Queue | Managed background processing |
| **Deployment** | Docker Compose | Multi-container orchestration |

## Production Safety Notes

- Set `ENVIRONMENT=production` in deployment environments.
- Set a strong `SECRET_KEY` (32+ characters).
- Configure `CORS_ALLOWED_ORIGINS` to trusted domains only.
- Use the included PostgreSQL database for production reliability.
- Set `COOKIE_SECURE=true` behind HTTPS.
- Set `APP_ENCRYPTION_KEY` to enable encryption for stored API keys.
- Runtime diagnostics are available at `GET /admin/runtime-metrics` (admin-only).

## 💾 System Requirements

| Scenario | CPU | RAM | Storage | Use Case |
|----------|-----|-----|---------|----------|
| **Personal** | 2 cores | 2GB | 10GB | Single user |
| **Friend Group** | 4 cores | 4GB | 50GB | 2-10 people |
| **Growing Team** | 8 cores | 8GB | 100GB | 10-50 people |

See [RESOURCE_REQUIREMENTS.md](docs/RESOURCE_REQUIREMENTS.md) for deployment sizing details.

##  Workflow Overview


1. **Upload Lecture**: PDF, PPTX, or images
2. **Auto Extract**: Font-aware extraction + table detection → clean markdown
3. **Organize**: Assign to subject + group (e.g., "Semester 1 → Math")
4. **Review & Edit**: Built-in markdown editor with live preview
5. **Search & Chat**: Semantic search + RAG-powered Q&A
6. **Generate Materials**: Quizzes, study guides
7. **Track Progress**: Monitor study sessions via analytics dashboard

## 💡 Use Cases

- **Students**: Convert lecture PDFs → study materials automatically
- **Study Groups**: Collaborative note-taking with shared AI resources
- **Instructors**: Convert course materials to student-friendly formats
- **Self-Learners**: Build searchable knowledge base from online courses
- **Research**: Extract structured data from academic papers
