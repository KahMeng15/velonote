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
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment to keep dependencies isolated
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .

# Download and install torch separately (download-r2.pytorch.org CDN has SSL handshake failure)
# Use Python's urllib which works with download.pytorch.org directly
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install certifi
# Download torch CPU wheel via urllib (download-r2.pytorch.org CDN has broken TLS)
RUN python3 << 'PYEOF'
import urllib.request, urllib.parse, os, sys, platform
from html.parser import HTMLParser
from urllib.parse import urljoin

BASE = 'https://download.pytorch.org'

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for name, value in attrs:
                if name == 'href' and '.whl' in value:
                    self.links.append(value.split('#')[0])

resp = urllib.request.urlopen(f'{BASE}/whl/cpu/torch/')
p = Parser()
p.feed(resp.read().decode())
links = p.links

tag = f'cp{sys.version_info.major}{sys.version_info.minor}-cp{sys.version_info.major}{sys.version_info.minor}'
machine = platform.machine()
match = [l for l in links if l.endswith('.whl') and tag in l and machine in l and 'manylinux' in l]
if not match:
    print(f'No torch wheel for {tag} on {machine}'); sys.exit(1)

# Handle relative URLs from the directory listing
raw_url = match[-1]
if raw_url.startswith('/'):
    raw_url = urljoin(BASE, raw_url)
elif not raw_url.startswith('http'):
    raw_url = urljoin(BASE + '/whl/cpu/torch/', raw_url)
url = raw_url.replace('download-r2.pytorch.org', 'download.pytorch.org')
name = urllib.parse.unquote(url.rsplit('/', 1)[-1])
path = f'/tmp/torch-wheels/{name}'
os.makedirs('/tmp/torch-wheels', exist_ok=True)
if not os.path.exists(path):
    print(f'Downloading {name}...')
    urllib.request.urlretrieve(url, path)
PYEOF
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /tmp/torch-wheels/torch-*.whl && \
    grep -v '^torch' requirements.txt > /tmp/requirements-notorch.txt && \
    pip install --default-timeout=1000 --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements-notorch.txt


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

# Install runtime dependencies (e.g., Tesseract for OCR, Poppler for PDF images, OpenCV deps, and FFmpeg for audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    gosu \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY . .

# Define build arguments for UID and GID (defaults to TrueNAS 'apps' user)
ARG USER_ID=568
ARG GROUP_ID=568

# Create non-root user and setup directories
RUN groupadd --gid ${GROUP_ID} appgroup \
    && useradd --create-home --shell /usr/sbin/nologin --uid ${USER_ID} --gid ${GROUP_ID} appuser \
    && mkdir -p /app/data /app/logs \
    && chown -R appuser:appgroup /app

# Prepare entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose port
EXPOSE 8000

# Start as root to allow entrypoint to fix permissions
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
