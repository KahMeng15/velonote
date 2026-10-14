# --- Stage 1: Builder ---
FROM python:3.11-slim-bookworm AS builder

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    binutils \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment to keep dependencies isolated
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Prune virtual environment:
# 1. Remove test directories, caches, and unnecessary files across packages
RUN find /opt/venv -type d \( -name "tests" -o -name "test" -o -name "__pycache__" \) -exec rm -rf {} + 2>/dev/null || true

# 2. Remove build utilities from the production virtual environment
RUN pip uninstall -y pip setuptools wheel


# --- Stage 2: Runtime ---
FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/kahmeng15/velonote"
LABEL org.opencontainers.image.description="velonote - AI-Powered Study Companion"
LABEL org.opencontainers.image.licenses="MIT"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    ENVIRONMENT=production

WORKDIR /app

# Prevent installing documentation/man pages in debian packages
RUN printf 'path-exclude=/usr/share/doc/*\npath-exclude=/usr/share/man/*\npath-exclude=/usr/share/locale/*\n' > /etc/dpkg/dpkg.cfg.d/01_nodoc

# Install runtime dependencies (Tesseract for OCR, Poppler for PDF images, OpenCV deps, FFmpeg, and postgresql-client for backups)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    postgresql-client \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    gosu \
    ffmpeg \
    && rm -rf /usr/share/doc/* /usr/share/man/*

# Define build arguments for UID and GID (defaults to TrueNAS 'apps' user)
ARG USER_ID=568
ARG GROUP_ID=568

# Create non-root user and persistent directories before copying application code
RUN groupadd --gid ${GROUP_ID} appgroup \
    && useradd --create-home --shell /usr/sbin/nologin --uid ${USER_ID} --gid ${GROUP_ID} appuser \
    && mkdir -p /app/data /app/logs /app/backups /app/config \
    && chown -R appuser:appgroup /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Prepare entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy application code with non-root ownership (avoids duplicated overlay layer from chown -R)
COPY --chown=appuser:appgroup . .

# Expose port
EXPOSE 8000

# Start as root to allow entrypoint to fix permissions
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
