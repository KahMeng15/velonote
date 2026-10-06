# velonote - AI-Powered Study Companion

## 📖 Project Overview
velonote is a multi-container web application designed to convert lecture materials (PDF, PPTX, images) into structured, AI-enhanced study notes. It utilizes a sophisticated processing pipeline to extract clean markdown, which then enables features like RAG-based chat, quiz generation, and progress tracking.

### Architecture & Tech Stack
- **Backend**: FastAPI (Python 3.11+)
- **Worker**: Dedicated Python process for background tasks (OCR, AI, Embeddings).
- **Frontend**: React (Vite), styled with Mantine UI.
- **Database**: **PostgreSQL 15** (managed via SQLAlchemy ORM).
- **AI/LLM**: Supports Google Gemini (default), Hugging Face, and Ollama.
- **Vector Search**: Local embeddings (`sentence-transformers/all-MiniLM-L6-v2`) stored in PostgreSQL.
- **Deployment**: Orchestrated via **Docker Compose**.

## 🚀 Building and Running

### Development Environment (Local)
To run the project locally for development with hot-reloading:
```bash
# 1. Start Infrastructure (Database + Redis)
docker-compose up -d db redis

# 2. Setup virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env to add your API keys. Do NOT set DATABASE_URL — it's auto-constructed from DB_USER/PASSWORD/HOST/PORT/NAME.

# 4. Run API, Worker, and Frontend (Local or Containerized)
./scripts/dev.sh              # Local (Python + Node on host)
# OR Run full containerized dev stack with file watchers:
docker compose -f docker-compose.dev.yml up
```

### Docker Deployment
The recommended way to deploy the full stack:
```bash
docker-compose up -d --build
```
- **Web UI**: `http://localhost:8000`
- **API Docs**: `http://localhost:8000/docs`

### Testing
No Python test suite exists. Offline extraction test:
```bash
python scripts/ProcessingAlgorithmTest/run_smart.py
```

## 🛠️ Development Conventions

### Project Structure
- `app/main.py`: API entry point and middleware configuration.
- `app/worker_main.py`: Background task consumer.
- `app/processing/smart_pipeline.py`: Core extraction logic (Font-aware + AI Polish).
- `app/routers/`: Modular API endpoints.
- `app/models/db.py`: SQLAlchemy models for PostgreSQL.
- `app/schemas/schemas.py`: Pydantic models for request/response validation.

### Background Tasks
Tasks (OCR, AI generation, Embeddings) are managed via a database-backed queue. The API submits a `Task` record, which is then picked up and processed by the dedicated `Worker` service.

### Security & Authentication
- **JWT Auth**: Uses stateless JSON Web Tokens with a "sliding session" (re-issued on activity).
- **CSRF Protection**: Enforced for cookie-authenticated sessions.
- **IP Filtering & Lockdown Mode**: Configurable via the admin dashboard and `IPFilter` model.

### Logging
The system writes logs to `./logs/` (3 files: `api.log`, `worker.log`, `errors.log`) via `app/logging_config.py`.

### UI Development
The frontend is built with React, Vite, and Mantine UI. It handles its own routing using `react-router-dom` and interacts with the FastAPI backend via REST endpoints.
