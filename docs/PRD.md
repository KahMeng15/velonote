# Product Requirements Document (PRD): velonote

## 1. Product Overview
**velonote** is a multi-container, AI-powered study companion web application. Its primary goal is to convert unstructured or semi-structured lecture materials (such as PDFs, PowerPoint presentations, and images) into structured, AI-enhanced study notes. By utilizing a sophisticated data processing pipeline to extract clean markdown, velonote unlocks advanced learning capabilities including Retrieval-Augmented Generation (RAG)-based chat, automated quiz generation, and personalized progress tracking.

## 2. Target Audience
- **Students (High School, University, Graduate):** Needs to process massive amounts of lecture slides and reading materials efficiently.
- **Professionals & Lifelong Learners:** Requires tools to quickly synthesize reports, research papers, and presentations into actionable notes.
- **Educators:** Looking for tools to rapidly generate study guides, summaries, and quizzes from their source materials.

## 3. Core Features & Requirements

### 3.1 Document Ingestion & Processing Pipeline
- **File Uploads:** Support for importing `.pdf`, `.pptx`, and image files.
- **Smart Extraction:** A font-aware extraction process that accurately captures document hierarchy and structure.
- **OCR (Optical Character Recognition):** Capability to read text from image-based PDFs and standalone images.
- **AI Polish:** Refines extracted raw text into clean, readable Markdown formats.
- **Asynchronous Processing:** Heavy tasks (OCR, AI, Embeddings) must be handled by a background worker queue to keep the frontend responsive.

### 3.2 AI & Learning Tools
- **Interactive RAG Chat:** Users can chat directly "with their documents". The system uses vector search to retrieve relevant context from notes to answer user queries accurately.
- **Quiz Generation:** The AI analyzes the structured markdown to automatically generate study quizzes (e.g., flashcards, multiple-choice).
- **Progress Tracking:** Monitors the user's study progress, quiz results, and interaction with the material.

### 3.3 Flexible AI & LLM Integration
- **Default Provider:** Google Gemini API for fast, high-quality generation.
- **Alternative Providers:** Support for Hugging Face and local inference via Ollama, allowing for privacy-focused or offline use-cases.
- **Vector Embeddings:** Uses local embeddings (`sentence-transformers/all-MiniLM-L6-v2`) to generate document vectors.

### 3.4 User Interface & Experience
- **Responsive Web App:** Built as a Single Page Application (SPA).
- **Design System:** Utilizes Mantine UI for a clean, accessible, and modern aesthetic.
- **Note Management:** A dashboard to view, edit, search, and manage generated notes.

### 3.5 Security & Administration
- **Authentication:** Secure user login using stateless JSON Web Tokens (JWT) with sliding sessions (tokens are re-issued upon activity).
- **Session Security:** CSRF protection enforced for cookie-authenticated sessions.
- **Admin Controls:** An administration dashboard featuring configurable IP filtering and a "Lockdown Mode" to restrict access.

## 4. Technical Architecture

### 4.1 Technology Stack
- **Frontend:** React, Vite, Mantine UI, `react-router-dom`.
- **Backend API:** FastAPI (Python 3.11+).
- **Background Worker:** Dedicated Python process consuming a database-backed task queue.
- **Database:** PostgreSQL 15 (managed via SQLAlchemy ORM). Used for relational data and vector storage (embeddings stored as JSON in the `lecture_embeddings` table).
- **Caching/Queue:** Redis (used alongside PostgreSQL for infrastructure).

### 4.2 System Components
- `app/main.py`: Main FastAPI entry point and middleware.
- `app/routers/`: Modular API endpoints for the frontend to consume.
- `app/worker_main.py`: Background task consumer.
- `app/processing/smart_pipeline.py`: Core extraction logic.
- `app/models/db.py`: SQLAlchemy database models.

### 4.3 Deployment & Infrastructure
- **Containerization:** Fully orchestrated via Docker Compose.
- **Local Dev Environment:** Scripted setups (`./scripts/dev.sh`) with hot-reloading for API and Frontend.
- **Logging:** Granular logging system configured in `app/logging_config.py` that separates outputs into multiple log files in `./logs` based on module and worker type.

## 5. Future Considerations
- Expand supported file types (e.g., `.docx`, audio/video transcription).
- Collaborative features for sharing notes and quizzes among peers.
- Mobile application or Progressive Web App (PWA) optimization.
