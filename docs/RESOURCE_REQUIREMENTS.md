# Resource Requirements & Sizing Guide

velonote is designed to be efficient, but its multi-container architecture and AI components have specific resource needs. This guide helps you size your deployment based on expected usage.

## 💻 Hardware Requirements

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| **CPU** | 2 Cores | 4+ Cores | Multi-container overhead and PDF/OCR extraction. |
| **RAM** | 2 GB | 4 GB | Shared across API, Worker, and Postgres. `sentence-transformers` uses ~600MB. |
| **Storage** | 10 GB | 50+ GB | Depends on the number of uploaded documents and Postgres data. |

---

## 📊 Usage Scenarios

### Personal Use (1 User)
- **CPU**: 2 Cores
- **RAM**: 2 GB
- **Storage**: 10 GB
- **Experience**: Responsive UI and reliable background processing.

### Friend Group (2-10 Users)
- **CPU**: 4 Cores
- **RAM**: 4 GB
- **Storage**: 50 GB
- **Experience**: Handles concurrent uploads and multiple chat sessions smoothly thanks to dedicated workers.

### Small Class / Team (10-50 Users)
- **CPU**: 8 Cores
- **RAM**: 8 GB
- **Storage**: 100 GB
- **Experience**: Recommended for high-volume processing and many concurrent users.

---

## 🧠 AI Resource Impact

### 1. Local Embeddings (`sentence-transformers`)
The `all-MiniLM-L6-v2` model is used for semantic search, running on the **Worker** service.
- **Memory**: Consumes ~400-600MB resident memory on the Worker container.
- **CPU**: Spikes during the "Embedding" phase of document processing.

### 2. LLM Providers
- **Gemini / Hugging Face**: Minimal local resource impact (API-based).
- **Ollama (Local LLM)**: **Significant impact.**
  - If running Ollama on the same machine, you need an additional **8GB+ RAM** and ideally a GPU.

### 3. OCR (Tesseract)
- **CPU**: High impact during OCR of large PDFs, handled by the Worker service.

### 4. Redis Cache
- **Memory**: Minimal resource impact (~10-50MB resident memory on the Redis container).
- **Network/Performance**: High-speed database query caching, user session state tracking, and API rate-limiting lookups.

---

## 💾 Storage Management

velonote stores data in several locations, all of which should be persisted via Docker volumes:
1. **PostgreSQL Data**: Stored in `./data/postgres`. This grows with notes, chat history, and vector embeddings.
2. **Original Uploads**: Stored in `./data/uploads`. This is the primary driver of storage usage.
3. **Generated Materials**: Stored in `./data/generated`. Contains AI-generated study aids and version snapshots.
4. **Logs**: Stored in `./logs`. Aggregated logs from all services.

**Recommendation**: Ensure the `./data` and `./logs` directories are mounted as volumes in your `docker-compose.yml` to ensure data persistence and easy monitoring.
