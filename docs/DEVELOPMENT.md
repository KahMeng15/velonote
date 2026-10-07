# Development Guide

This guide is for developers who want to contribute to velonote or run it locally for development purposes. The application has been refactored into a **Multi-Container Architecture** to improve scalability and maintainability.

---

## 🏗️ Architecture Overview

The system consists of 5 primary services:
1.  **Frontend (React + Vite):** Dev server at `localhost:5173` with `/api` proxied to the API. Production builds are served by Nginx.
2.  **API (FastAPI):** Handles HTTP requests, authentication, and database operations.
3.  **Worker (Python):** Processes background tasks like OCR, AI processing, and embedding generation.
4.  **Database (PostgreSQL):** Persistent storage for application data and the task queue.
5.  **Cache (Redis):** High-speed in-memory caching for files and API responses.

---

## 🛠️ Quick Start (Docker - Recommended)

The easiest way to get started is using the pre-configured development Docker stack. This provides **hot-reloading** for both the API and the Worker.

### 1. Prerequisites
- **Docker** and **Docker Compose** installed.

### 2. Setup
```bash
# Clone the repository
git clone <repo-url> velonote
cd velonote

# Create a .env file from the example
cp .env.example .env
```
*Note: Ensure individual database variables in `.env` are set correctly. If running via Docker Compose, set `DB_HOST=db`. If running locally on the host machine, use `DB_HOST=localhost`.*

### 3. Start Development Environment
```bash
# Start all dev containers with file watchers
docker compose -f docker-compose.dev.yml up

# Or with built-in local Ollama:
docker compose -f docker-compose.dev.yml --profile builtin up

# Or using the dev script:
./scripts/dev.sh --docker
```
- **Frontend UI (Vite HMR):** [http://localhost:5173](http://localhost:5173)
- **API Server & OpenAPI Docs:** [http://localhost:8000](http://localhost:8000) / [http://localhost:8000/docs](http://localhost:8000/docs)
- **Postgres:** Exposed on port `5432` for local inspection.
- **Ollama:** Exposed on port `11434` (when running with `--profile builtin`).

---

## 💻 Local Terminal Development

If you prefer to run the Python code directly on your host machine for faster debugging:

### 1. Start Infrastructure
The application requires PostgreSQL. Keep the container running:
```bash
docker-compose up -d db
```

### 2. Install Local Dependencies
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the App & Worker
Use the provided development script to start both processes in a single terminal:
```bash
./scripts/dev.sh
```
This will start the **API** with hot-reload and the **Worker** as a background process.

---

## 📜 Logging System

Logs are stored in `./logs/` via `app/logging_config.py`:

| File | Description |
| :--- | :--- |
| `api.log` | All API request logs. |
| `worker.log` | Background worker logs. |
| `errors.log` | ERROR-level logs from all sources. |

---

## 🧪 Testing

No Python test suite exists. Offline extraction test (no server needed):
```bash
python scripts/ProcessingAlgorithmTest/run_smart.py
```

---

## 🔄 Common Development Tasks

### Modifying Background Tasks
Background tasks are managed in `app/utils/tasks.py`. 
1.  **Submission:** The API calls `TaskManager.submit_task()`, which serializes the request into the `tasks` table.
2.  **Processing:** The Worker (`app/worker_main.py`) polls for `pending` tasks and executes the corresponding handler.

### Modifying the Extraction Pipeline
The core logic resides in `app/processing/smart_pipeline.py`.
- Use `scripts/ProcessingAlgorithmTest/run_smart.py` to test extraction on specific files without booting the whole app.

### Database Migrations
Tables auto-created via `Base.metadata.create_all()` in `init_db()`. Schema changes go in `app/utils/db.py` as new `apply_*_migration()` functions called from `init_db()` — never hand-write SQL migration scripts.

### AI Configuration & 3-Tier Fallback
The AI client (`app/processing/ai_client.py`) is designed with a 3-tier fallback hierarchy to ensure robustness:
1. **Tier 1 (Primary)**: High-performance Reasoning LLM (default: `models/gemma-4-31b-it` via Gemini API).
2. **Tier 2 (Secondary)**: Fallback Reasoning LLM (default: `models/gemma-4-26b-a4b-it` via Gemini API).
3. **Tier 3 (Local Fallback)**: Offline/local model (default: `llama3` or `gemma4:e2b` via Ollama).

For testing LLM extraction behavior offline, use `scripts/ProcessingAlgorithmTest/run_smart.py`.

---

## 🛡️ Security Note
Never commit your `.env` file. It contains sensitive API keys and database credentials. A `.dockerignore` and `.gitignore` are pre-configured to prevent accidental exposure of logs and environment files.
