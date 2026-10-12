# velonote Technical Documentation

## 1. Introduction
velonote is an AI-powered study companion designed to convert lecture materials (PDF, PPTX, images) into structured, searchable, and interactive study notes. It provides students and small study groups with tools for semantic Q&A, quiz generation, and progress tracking.

The project is built with a focus on **scalability, reliability, and privacy**, using a **multi-container architecture** to separate API concerns from resource-intensive background processing.

---

## 2. Architecture & Tech Stack

velonote follows a modular, multi-service architecture designed for reliable performance.

### 2.1 Services
- **Frontend (Nginx)**: Serves static assets and acts as a reverse proxy for the API.
- **API (FastAPI)**: Handles HTTP requests, authentication, and database operations.
- **Worker (Python)**: Dedicated background process that polls for tasks (OCR, AI, Embeddings) and executes them.
- **Database (PostgreSQL)**: Persistent storage for application data and the task queue.
- **Cache (Redis)**: High-speed in-memory store for sessions, token validation, and rate limiting.

### 2.2 Stack
- **Backend Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 15 with SQLAlchemy ORM.
- **Vector Search**: Local embeddings generated via `sentence-transformers` and stored in PostgreSQL.
- **Background Tasks**: Managed via a DB-backed task queue processed by the dedicated worker.
- **AI Integration**: Custom `AIClient` supporting Google Gemini, Hugging Face Inference API, and local Ollama.

### 2.3 Frontend
- **Framework**: React 19 + Vite + Mantine UI 9.
- **Routing**: `react-router-dom` for client-side routing.
- **Markdown Rendering**: `react-markdown` with `remark-gfm` + `rehype-raw`.
- **Rich Text**: TipTap editor (Mantine integration) with table support.
- **Icons**: `@tabler/icons-react`.
- **Build System**: Vite dev server (hot-reload) at `localhost:5173`, proxies `/api` → API.
- **Real-time Updates**: WebSockets for live processing progress.

---

## 3. Data Models & Database Schema

The database consists of several key entities managed via SQLAlchemy:

- **User**: Authentication, personal AI configurations (OAuth metadata, credentials encryption key), failed login attempt lockouts, and Pomodoro timer preferences.
- **SubjectGroup**: Organizes subjects into higher-level course groups or semesters.
- **QuizGroup**: Organizes AI-generated quizzes into high-level categories.
- **Subject**: Individual courses or topics under a SubjectGroup.
- **Lecture**: The core document entity. Stores file metadata, original path, and generated output PDF path.
- **LectureEmbedding**: Stores vector embeddings and raw text chunks for semantic search.
- **Task**: Background processing queue items (OCR, embedding generation, summaries, AI polish).
- **ChatMessage**: Stores conversation history, supporting conversation threading (`conversation_id`), reply nesting (`reply_to_message_id`), response modes, custom output formats, timing logs, and pinned/favourite status.
- **ExportTemplate**: Stores user-defined layouts, styles, and settings for document exports.
- **Quiz**: Stores quizzes scoped by group, subject, or lecture.
- **QuizQuestion**: Stores individual questions, optional JSON choices (for objective types), and detailed explanations.
- **QuizProgress**: Tracks Spaced Repetition (SRS) parameters (`interval_days`, `ease_factor`, `consecutive_correct`) for student review schedules.
- **StudySession**: Tracks time spent studying, session type (quiz, chat, pomodoro, stopwatch), and user score performance.
- **Summary**: Stores versioned summaries, cheat sheets, formatting modes, and custom outputs.
- **SystemSettings**: Global configuration (Maintenance Mode, Lockdown Mode, sign-up rules, sliding session lengths, and global AI models).
- **UserInvitation**: Manages pending registration invitation tokens.
- **PasswordResetToken / EmailVerificationToken / PasswordChangeConfirmation**: Handles verification, reset, and confirmation tokens for security flows.
- **UserLog**: Centralized actions audit trail (pages accessed, logs generated, etc.).
- **IPBlock / IPFilter / RateLimitConfig**: Temporary IP block list for brute-force mitigation, IP blacklist/whitelist rules, and API rate-limiting rules.

---

## 4. Core Workflows

### 4.1 Document Processing Pipeline (`UnifiedContentProcessor`)
The new unified pipeline replaces the legacy `SmartPipeline` and provides a single entry point for all supported document types (PDF, PPTX, DOCX, images). It automatically detects scanned PDFs and routes them through the appropriate OCR workflow, while also handling native documents with font‑aware heading detection and table extraction.

1. **Submission**: User uploads a file → API creates a `process_resource` or `process_exercise` task in the `Task` table.
2. **Unified Extraction** (`UnifiedContentProcessor.extract()`):
   - Detects document type and whether it is scanned.
   - **PDF**: Uses `pdfplumber` for tables, `FontAwareExtractor` for headings, and `ImageExtractorV2` for images.
   - **PPTX**: Extracts text via `python-pptx` and images via `ImageExtractorV2`.
   - **DOCX**: Parses text with `python-docx` and extracts inline images.
   - **Images**: Directly processed as single‑page documents.
   - Scanned PDFs are handed to `ScannedDocHandler` → Tesseract OCR with `ImagePreprocessor`.
   - Extracted images are filtered by `ImageClassifier` and positioned inline by `ImageTextMapper`.
3. **Worker Processing**: The worker executes the unified extraction, generates embeddings, and stores a `ContentBundle` (markdown, images, metadata).
4. **AI Polish (Optional)**: The `AIClient` may be invoked to improve formatting, consistency, and add reasoning layers.
5. **Result**: Clean markdown plus extracted assets are saved for downstream features (RAG, quizzes, exports).

### 4.2 Semantic Search & RAG
velonote implements a "Zero-Config RAG" system:

1. **Chunking**: Extracted text is split into ~500-character chunks.
2. **Embedding**: Chunks are converted into 384-dimensional vectors using `sentence-transformers` on the Worker.
3. **Storage**: Vectors are stored in the `lecture_embeddings` table in PostgreSQL.
4. **Retrieval**: At query time, the user's question is embedded, and cosine similarity is calculated to find relevant chunks.
5. **Augmentation**: Top-K chunks are injected into the LLM prompt as context.

### 4.3 AI Integration (`AIClient` & 3-Tier Fallback)
The system abstracts AI providers into a unified `AIClient` utilizing a three-tier fallback architecture:

- **Tier 1 (Primary - Gemini)**: High-reasoning model (configured for `models/gemma-4-31b-it`). Automatically injects the reasoning depth header.
- **Tier 2 (Secondary - Gemini)**: Fallback reasoning model (configured for `models/gemma-4-26b-a4b-it`).
- **Tier 3 (Local Fallback - Ollama)**: Local LLM service (configured for local models like `llama3` or `gemma4:e2b`).

**Gemma-4 Reasoning Support**: The `AIClient` automatically intercepts and strips reasoning-specific tokens (such as `<think>`, `</think>`, `<|channel|>thought`, and `<|thought|>`) from streaming and unary responses, outputting polished Markdown directly.

### 4.4 Spaced Repetition System (SRS)
The application implements an automated quiz system powered by the **SuperMemo-2 (SM-2)** algorithm. When a user submits a quiz answer:
- **Correct Response**:
  - `consecutive_correct` is incremented.
  - If `consecutive_correct == 1`: review interval is set to 1 day.
  - If `consecutive_correct == 2`: review interval is set to 6 days.
  - If `consecutive_correct > 2`: review interval is set to `interval_days * ease_factor` (rounded to integer).
  - `ease_factor` increases by 0.1.
- **Incorrect Response**:
  - `consecutive_correct` is reset to 0.
  - `interval_days` is reset to 1 day.
  - `ease_factor` decreases by 0.2 (floor limit is 1.3).

The next review date is scheduled via `next_review_at` based on the computed `interval_days`.

---

## 5. Security & Governance

The middleware logic in `app/main.py` coordinates robust safety controls:
- **JWT Authentication**: Handles cookie-based and header-based session tokens with a sliding window.
- **Sliding Session Expiration**: If enabled in `SystemSettings`, active sessions are automatically re-issued new tokens and CSRF cookies on each API request.
- **Lockdown Mode**: Instantly blocks all incoming connections from non-local networks (allows only localhost/private IP ranges).
- **Maintenance Mode**: Restricts application access to administrators only, redirecting standard users to a status page.
- **IP Filtering**: Middleware whitelists or blacklists connections by specific IP addresses or countries.
- **Rate Limiting**: Enforces rate-limiting policies on critical endpoints (e.g., login, sign-up, document extraction) to mitigate DDoS and brute-force attacks.
- **Secrets Encryption**: Fernet-based encryption is used to secure user-configured API keys at rest in the database.

---

## 6. Directory Structure

```text
/
├── app/
│   ├── models/             # SQLAlchemy DB models
│   ├── processing/         # Core extraction & AI logic
│   ├── routers/            # FastAPI API endpoints
│   ├── utils/              # Utilities (Auth, Tasks, DB)
│   ├── main.py             # API entry point
│   └── worker_main.py      # Background worker entry point
├── frontend/               # React + Vite + Mantine UI
├── data/                   # Persistent storage (Postgres/Uploads)
├── docs/                   # Documentation files
├── logs/                   # Centralized logging directory
└── scripts/                # Utility & Dev scripts
```

---

## 7. Performance & Scaling

- **Worker Separation**: Decoupling processing from the API prevents the UI from becoming unresponsive during heavy tasks.
- **PostgreSQL**: Provides better concurrency and reliability than SQLite for multi-user environments.
- **Resource Usage**: Designed to run on modest hardware (4 vCPUs, 4GB RAM recommended for multi-container setup).

---

## 8. Development Guidelines

- **Database Migrations**: Managed via `app/utils/db.py`.
- **Worker Logic**: When adding new processing features, ensure they are integrated into the `Task` model and the `TASK_REGISTRY` in `worker_main.py`.
- **API**: Always use Pydantic schemas in `app/schemas/` for validation.
