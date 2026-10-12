"""Configuration management

Loading priority (highest → lowest):
  1. Real environment variables (docker / shell exports)
  2. secrets.env  — auto-generated secrets (SECRET_KEY, APP_ENCRYPTION_KEY, DB_PASSWORD)
  3. .env          — SMTP, AI tiers, Firebase, DB host/user/port, Redis, HOST, PORT
  4. config/app.config.json — non-sensitive runtime defaults (auto-created if absent)
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repository root — works whether running from the project root or inside app/
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent  # app/
_ROOT = _HERE.parent  # project root

_ENV_FILE = _ROOT / ".env"
_SECRETS_FILE = _ROOT / "secrets.env"
_CONFIG_DIR = _ROOT / "config"
_CONFIG_FILE = _CONFIG_DIR / "app.config.json"


# ---------------------------------------------------------------------------
# Hardcoded constants (not configurable via environment)
# ---------------------------------------------------------------------------
APP_NAME = "VeloNote"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
ALLOWED_EXTENSIONS = "pdf,pptx,png,jpg,jpeg"
OCR_ENABLED = True
AI_POLISH_ENABLED = True
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Database connection-pool defaults
DB_POOL_SIZE = 20
DB_MAX_OVERFLOW = 40
DB_POOL_TIMEOUT_SECONDS = 30
DB_POOL_RECYCLE_SECONDS = 1800


# ---------------------------------------------------------------------------
# Default non-sensitive config (written to app.config.json if absent)
# ---------------------------------------------------------------------------
_CONFIG_DEFAULTS: dict = {
    "ENVIRONMENT": "development",
    "DEBUG": False,
    "LOG_LEVEL": "INFO",
    "CORS_ALLOWED_ORIGINS": "http://localhost:8000,http://127.0.0.1:8000",
    "COOKIE_SECURE": False,
    "COOKIE_SAMESITE": "lax",
    "CSRF_COOKIE_NAME": "csrf_token",
    "CSRF_HEADER_NAME": "X-CSRF-Token",
    "MAX_UPLOAD_SIZE_MB": 50,
    "TASK_RETENTION_DAYS": 14,
    "CACHE_TTL_SECONDS": 3600,
    "ADMIN_EMAIL": "",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_config_file() -> dict:
    """Create config/app.config.json with defaults if it does not exist."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not _CONFIG_FILE.exists():
        _CONFIG_FILE.write_text(json.dumps(_CONFIG_DEFAULTS, indent=2) + "\n", encoding="utf-8")
        print(
            f"[velonote] Created default config file: {_CONFIG_FILE}",
            file=sys.stderr,
        )
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[velonote] WARNING: Could not parse {_CONFIG_FILE}: {exc}", file=sys.stderr)
        return {}


def _generate_secrets() -> None:
    """Generate missing secrets and append them to secrets.env."""
    existing = dotenv_values(_SECRETS_FILE) if _SECRETS_FILE.exists() else {}

    lines_to_append: list[str] = []

    if not existing.get("SECRET_KEY"):
        key = secrets.token_hex(32)
        lines_to_append.append(f"SECRET_KEY={key}")
        print(
            "[velonote] Generated new SECRET_KEY → secrets.env",
            file=sys.stderr,
        )

    if not existing.get("APP_ENCRYPTION_KEY"):
        try:
            from cryptography.fernet import Fernet

            fernet_key = Fernet.generate_key().decode()
        except ImportError:
            # Fallback if cryptography isn't installed yet
            fernet_key = secrets.token_urlsafe(32)
        lines_to_append.append(f"APP_ENCRYPTION_KEY={fernet_key}")
        print(
            "[velonote] Generated new APP_ENCRYPTION_KEY → secrets.env",
            file=sys.stderr,
        )

    if not existing.get("DB_PASSWORD"):
        db_pass = secrets.token_urlsafe(24)
        lines_to_append.append(f"DB_PASSWORD={db_pass}")
        print(
            "[velonote] Generated new DB_PASSWORD → secrets.env",
            file=sys.stderr,
        )

    if lines_to_append:
        with _SECRETS_FILE.open("a", encoding="utf-8") as fh:
            if _SECRETS_FILE.stat().st_size > 0:
                fh.write("\n")
            fh.write("\n".join(lines_to_append) + "\n")


def _load_env_files() -> dict[str, str | None]:
    """Merge .env + secrets.env into a single dict (real env vars take precedence)."""
    base = dotenv_values(_ENV_FILE) if _ENV_FILE.exists() else {}
    secrets_vals = dotenv_values(_SECRETS_FILE) if _SECRETS_FILE.exists() else {}
    # secrets.env values override .env (so generated values aren't shadowed)
    merged = {**base, **secrets_vals}
    # Real environment variables always win
    for key in list(merged.keys()):
        if key in os.environ:
            merged[key] = os.environ[key]
    return merged


# ---------------------------------------------------------------------------
# Bootstrap — run once at import time (before Settings is constructed)
# ---------------------------------------------------------------------------
_json_config = _ensure_config_file()
_generate_secrets()


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Application settings.

    Values are resolved in this order:
      env var > secrets.env > .env > app.config.json default > field default
    """

    # ------------------------------------------------------------------
    # Sensitive / host-specific  (.env)
    # ------------------------------------------------------------------

    # Database
    DB_USER: str = "velonote"
    DB_PASSWORD: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "velonote"

    # Database Backups
    BACKUP_DIR: str = "backups/postgres"

    # Redis (deprecated - cache is now in-memory)
    REDIS_URL: str = ""

    # JWT — auto-generated into secrets.env on first run
    SECRET_KEY: str = ""

    # Encryption — auto-generated into secrets.env on first run
    APP_ENCRYPTION_KEY: str = ""

    # Server
    HOST: str = "0.0.0.0"  # nosec
    API_PORT: int = 8000  # uvicorn bind port (internal)
    FRONTEND_PORT: int = 5173  # vite dev server port (development)
    PUBLIC_PORT: int = 3000  # nginx / host-facing port (external)

    # SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SENDER_NAME: str = "VeloNote"
    SMTP_TLS: bool = True

    # ==================================================================
    # AI Configuration — Category 1: Chat / Instant Response
    # ==================================================================
    # Used for conversational chat, query rewrite, voice, and instant grading.
    # Prioritizes low latency and fast time-to-first-token.
    AI_CHAT_TIER1_PROVIDER: str = "groq"
    AI_CHAT_TIER1_MODEL: str = "llama-3.1-8b-instant"
    AI_CHAT_TIER1_API_KEY: str = ""
    AI_CHAT_TIER1_REASONING_LEVEL: str = "low"
    AI_CHAT_TIER1_BASE_URL: str = ""

    AI_CHAT_TIER2_PROVIDER: str = "gemini"
    AI_CHAT_TIER2_MODEL: str = "gemini-2.5-flash"
    AI_CHAT_TIER2_API_KEY: str = ""
    AI_CHAT_TIER2_REASONING_LEVEL: str = ""
    AI_CHAT_TIER2_BASE_URL: str = ""

    AI_CHAT_TIER3_PROVIDER: str = ""
    AI_CHAT_TIER3_MODEL: str = ""
    AI_CHAT_TIER3_API_KEY: str = ""
    AI_CHAT_TIER3_REASONING_LEVEL: str = ""
    AI_CHAT_TIER3_BASE_URL: str = ""

    # ==================================================================
    # AI Configuration — Category 2: Document Processing & Heavy Tasks
    # ==================================================================
    # Used for document extraction polish, notes generation, and exercises.
    # Prioritizes formatting accuracy, instruction adherence, and larger context.
    AI_PROCESSING_TIER1_PROVIDER: str = "ollama"
    AI_PROCESSING_TIER1_MODEL: str = "qwen2.5:1.5b"
    AI_PROCESSING_TIER1_API_KEY: str = ""
    AI_PROCESSING_TIER1_REASONING_LEVEL: str = "low"
    AI_PROCESSING_TIER1_BASE_URL: str = "http://ollama:11434"

    AI_PROCESSING_TIER2_PROVIDER: str = "groq"
    AI_PROCESSING_TIER2_MODEL: str = "llama-3.3-70b-versatile"
    AI_PROCESSING_TIER2_API_KEY: str = ""
    AI_PROCESSING_TIER2_REASONING_LEVEL: str = "low"
    AI_PROCESSING_TIER2_BASE_URL: str = ""

    AI_PROCESSING_TIER3_PROVIDER: str = "gemini"
    AI_PROCESSING_TIER3_MODEL: str = "models/gemma-4-26b-a4b-it"
    AI_PROCESSING_TIER3_API_KEY: str = ""
    AI_PROCESSING_TIER3_REASONING_LEVEL: str = "high"
    AI_PROCESSING_TIER3_BASE_URL: str = ""

    AI_PROCESSING_TIER4_PROVIDER: str = ""
    AI_PROCESSING_TIER4_MODEL: str = ""
    AI_PROCESSING_TIER4_API_KEY: str = ""
    AI_PROCESSING_TIER4_REASONING_LEVEL: str = ""
    AI_PROCESSING_TIER4_BASE_URL: str = ""

    # Legacy Global AI Configuration (fallback if category-specific vars are unset)
    GLOBAL_AI_TIER1_PROVIDER: str = ""
    GLOBAL_AI_TIER1_MODEL: str = ""
    GLOBAL_AI_TIER1_API_KEY: str = ""
    GLOBAL_AI_TIER1_REASONING_LEVEL: str = ""
    GLOBAL_AI_TIER1_BASE_URL: str = ""

    GLOBAL_AI_TIER2_PROVIDER: str = ""
    GLOBAL_AI_TIER2_MODEL: str = ""
    GLOBAL_AI_TIER2_API_KEY: str = ""
    GLOBAL_AI_TIER2_REASONING_LEVEL: str = ""
    GLOBAL_AI_TIER2_BASE_URL: str = ""

    GLOBAL_AI_TIER3_PROVIDER: str = ""
    GLOBAL_AI_TIER3_MODEL: str = ""
    GLOBAL_AI_TIER3_API_KEY: str = ""
    GLOBAL_AI_TIER3_BASE_URL: str = ""
    GLOBAL_AI_TIER3_REASONING_LEVEL: str = ""

    GLOBAL_AI_TIER4_PROVIDER: str = ""
    GLOBAL_AI_TIER4_MODEL: str = ""
    GLOBAL_AI_TIER4_API_KEY: str = ""
    GLOBAL_AI_TIER4_REASONING_LEVEL: str = ""
    GLOBAL_AI_TIER4_BASE_URL: str = ""

    # Legacy / individual AI fallbacks
    GEMINI_API_KEY: str = ""
    HUGGINGFACE_TOKEN: str = ""
    AI_PROVIDER: str = "gemini"
    OLLAMA_BASE_URL: str = ""

    # Firebase (public config served via /auth/firebase-config)
    FIREBASE_API_KEY: str = ""
    FIREBASE_AUTH_DOMAIN: str = ""
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_STORAGE_BUCKET: str = ""
    FIREBASE_MESSAGING_SENDER_ID: str = ""
    FIREBASE_APP_ID: str = ""
    FIREBASE_MEASUREMENT_ID: str = ""

    # ------------------------------------------------------------------
    # Non-sensitive  (app.config.json → env var override)
    # ------------------------------------------------------------------

    # Runtime
    ENVIRONMENT: str = _json_config.get("ENVIRONMENT", "development")
    DEBUG: bool = _json_config.get("DEBUG", False)
    LOG_LEVEL: str = _json_config.get("LOG_LEVEL", "INFO")

    # CORS / Session / CSRF
    CORS_ALLOWED_ORIGINS: str = _json_config.get(
        "CORS_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    )
    COOKIE_SECURE: bool = _json_config.get("COOKIE_SECURE", False)
    COOKIE_SAMESITE: str = _json_config.get("COOKIE_SAMESITE", "lax")
    CSRF_COOKIE_NAME: str = _json_config.get("CSRF_COOKIE_NAME", "csrf_token")
    CSRF_HEADER_NAME: str = _json_config.get("CSRF_HEADER_NAME", "X-CSRF-Token")

    # Uploads / tasks / cache
    MAX_UPLOAD_SIZE_MB: int = _json_config.get("MAX_UPLOAD_SIZE_MB", 50)
    TASK_RETENTION_DAYS: int = _json_config.get("TASK_RETENTION_DAYS", 14)
    CACHE_TTL_SECONDS: int = _json_config.get("CACHE_TTL_SECONDS", 3600)

    # Admin bootstrap
    ADMIN_EMAIL: str = _json_config.get("ADMIN_EMAIL", "")

    # Cloudflare Turnstile (bot protection) — no default; omit to disable
    TURNSTILE_SITE_KEY: str = _json_config.get("TURNSTILE_SITE_KEY", "")
    TURNSTILE_SECRET_KEY: str = _json_config.get("TURNSTILE_SECRET_KEY", "")

    # ------------------------------------------------------------------
    # Computed / constant pass-throughs
    # ------------------------------------------------------------------

    @property
    def APP_NAME(self) -> str:
        return APP_NAME

    @property
    def ALGORITHM(self) -> str:
        return ALGORITHM

    @property
    def ACCESS_TOKEN_EXPIRE_MINUTES(self) -> int:
        return ACCESS_TOKEN_EXPIRE_MINUTES

    @property
    def ALLOWED_EXTENSIONS(self) -> str:
        return ALLOWED_EXTENSIONS

    @property
    def OCR_ENABLED(self) -> bool:
        return OCR_ENABLED

    @property
    def EMBEDDING_MODEL(self) -> str:
        return EMBEDDING_MODEL

    @property
    def AI_POLISH_ENABLED(self) -> bool:
        return AI_POLISH_ENABLED

    @property
    def DB_POOL_SIZE(self) -> int:
        return DB_POOL_SIZE

    @property
    def DB_MAX_OVERFLOW(self) -> int:
        return DB_MAX_OVERFLOW

    @property
    def DB_POOL_TIMEOUT_SECONDS(self) -> int:
        return DB_POOL_TIMEOUT_SECONDS

    @property
    def DB_POOL_RECYCLE_SECONDS(self) -> int:
        return DB_POOL_RECYCLE_SECONDS

    @property
    def DATABASE_URL(self) -> str:
        """Construct SQLAlchemy database URL from individual components."""
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    class Config:
        # Load .env first, then secrets.env (later entries win for duplicates)
        env_file = (str(_ENV_FILE), str(_SECRETS_FILE))
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
