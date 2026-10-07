"""Main application entry point"""

import os
import sys
import time
import uuid

# Monkeypatch bcrypt for passlib compatibility (fix for bcrypt 4.1.0+)
try:
    import bcrypt

    if not hasattr(bcrypt, "__about__"):

        class BcryptAbout:
            def __init__(self, version):
                self.__version__ = version

        bcrypt.__about__ = BcryptAbout(getattr(bcrypt, "__version__", "unknown"))
except ImportError:
    pass
except Exception:
    pass
from collections import defaultdict, deque
from threading import Lock

# Ensure the current directory is in the path for module resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

# Configure logging
from app.logging_config import setup_logging
from app.routers import (
    admin,
    analytics,
    auth,
    chat,
    exercises,
    groups,
    logs,
    notes,
    processing,
    prompts,
    resources,
    search,
    snapshots,
    study_sessions,
    subjects,
    support,
    templates,
    voice,
    ws,
)
from app.utils.db import init_db
from app.utils.observability import record_request

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


def _is_production() -> bool:
    return settings.ENVIRONMENT.lower() == "production"


def _parse_cors_origins() -> list[str]:
    origins = [
        origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()
    ]
    if not origins:
        return ["http://localhost:8000", "http://127.0.0.1:8000"]
    return origins


def _validate_production_settings() -> None:
    if not _is_production():
        return

    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        raise RuntimeError(
            "Production startup blocked: SECRET_KEY must be set to at least 32 characters"
        )

    if "postgresql" not in settings.DATABASE_URL:
        raise RuntimeError("Production startup blocked: Only PostgreSQL is supported.")

    if "*" in _parse_cors_origins():
        raise RuntimeError("Production startup blocked: wildcard CORS origin is not allowed")


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _validate_production_settings()
    logger.info(f"Starting {settings.APP_NAME}")
    init_db()
    logger.info("Database initialized")

    logger.info("In-memory cache initialized")

    try:
        from app.utils.tasks import TaskManager

        deleted = TaskManager.cleanup_old_tasks()
        if deleted:
            logger.info(f"Cleaned up {deleted} old task records")
    except Exception as e:
        logger.warning(f"Task cleanup startup warning: {e}")

    # Seed default export templates
    from app.utils.db import SessionLocal

    try:
        db = SessionLocal()
        templates.seed_default_templates(db)

        # Bootstrap System Settings from .env defaults
        from app.models.db import SystemSettings

        sys_settings = db.query(SystemSettings).first()
        if not sys_settings:
            logger.info("Initializing SystemSettings from .env defaults")
            sys_settings = SystemSettings(
                global_ai_provider=settings.GLOBAL_AI_TIER1_PROVIDER,
                global_ai_model=settings.GLOBAL_AI_TIER1_MODEL,
            )

            db.add(sys_settings)
            db.commit()

        # Bootstrap Admin
        if settings.ADMIN_EMAIL:
            from app.models.db import User

            admin_user = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
            if admin_user:
                if not admin_user.is_admin:
                    logger.info(f"Elevating user to admin: {settings.ADMIN_EMAIL}")
                    admin_user.is_admin = True
                    db.commit()
            else:
                logger.debug(
                    f"Admin bootstrap: User {settings.ADMIN_EMAIL} not found. Register this account to enable admin access."
                )

        db.close()
    except Exception as e:
        logger.warning(f"Startup initialization warning: {e}")

    yield
    # Shutdown
    logger.info("Shutting down application")


# Initialize app
app = FastAPI(
    title=settings.APP_NAME,
    description="Simple AI-powered study assistant",
    version="1.0.0",
    lifespan=lifespan,
)

_rate_limit_lock = Lock()
_rate_limit_buckets = defaultdict(deque)

# Endpoint-level burst controls for abuse-prone routes.
_RATE_LIMIT_POLICY = {
    "/auth/login": (10, 60),
    "/auth/google-login": (20, 60),
    "/auth/password-reset-request": (5, 3600),
    "/processing/smart-extract": (6, 60),
    "/processing/smart-extract/download": (6, 60),
}

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-CSRF-Token"],
)

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.models.db import IPFilter, SystemSettings
from app.utils.db import SessionLocal
from app.utils.turnstile import turnstile_middleware

# Custom exception handlers — API-only JSON responses
_CAT_BASE = "https://http.cat"


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = exc.status_code
    return JSONResponse(
        status_code=code,
        content={"detail": exc.detail, "cat_url": f"{_CAT_BASE}/{code}"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "cat_url": f"{_CAT_BASE}/500"},
    )


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started_at = time.time()

    response = await call_next(request)
    duration_ms = int((time.time() - started_at) * 1000)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    if _is_production():
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    logger.info(
        "request.completed",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    record_request(request.url.path, response.status_code, duration_ms)
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    policy = _RATE_LIMIT_POLICY.get(request.url.path)
    if not policy:
        return await call_next(request)

    max_requests, window_seconds = policy
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.url.path}"
    now = time.time()

    with _rate_limit_lock:
        bucket = _rate_limit_buckets[key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()

        if len(bucket) >= max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please retry later."},
            )

        bucket.append(now)

    return await call_next(request)


app.middleware("http")(turnstile_middleware)


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return await call_next(request)

    csrf_exempt_paths = {
        "/auth/login",
        "/auth/google-login",
        "/auth/google-complete",
        "/auth/register",
        "/auth/resend-verification",
        "/auth/password-reset-request",
        "/auth/password-reset",
        "/auth/logout",
        "/auth/verify-email",
    }
    if request.url.path in csrf_exempt_paths:
        return await call_next(request)

    cookie_token = request.cookies.get("access_token")
    # Enforce CSRF only for cookie-authenticated browser sessions.
    if not cookie_token:
        return await call_next(request)

    csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
    csrf_header = request.headers.get(settings.CSRF_HEADER_NAME)
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})

    return await call_next(request)


@app.middleware("http")
async def system_settings_middleware(request: Request, call_next):
    db = SessionLocal()
    try:
        sys_settings = db.query(SystemSettings).first()
        client_ip = request.client.host if request.client else "127.0.0.1"

        if sys_settings:
            # 1. Lockdown Mode: allow local IPs only
            if sys_settings.lockdown_mode:
                if not (
                    client_ip.startswith("127.")
                    or client_ip.startswith("192.168.")
                    or client_ip.startswith("10.")
                    or client_ip == "::1"
                ):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "System is in Lockdown Mode. Local network access only."
                        },
                    )

            # 2. Maintenance Mode
            # Allow /admin, /auth, /login, /maintenance, and /static files to bypass
            bypass_paths = ["/admin", "/auth"]
            is_bypassed = any(request.url.path.startswith(path) for path in bypass_paths)

            if sys_settings.maintenance_mode and not is_bypassed:
                # 2a. Allow admin bypass if authenticated
                is_admin = False
                auth_header = request.headers.get("Authorization")
                cookie_token = request.cookies.get("access_token")
                token = None
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                elif cookie_token:
                    token = cookie_token

                if token:
                    try:
                        from app.utils.auth import decode_token, token_version_matches_user

                        payload = decode_token(token)
                        if payload:
                            u_id = payload.get("sub")
                            if u_id:
                                from app.models.db import User

                                user = db.query(User).filter(User.id == int(u_id)).first()
                                if (
                                    user
                                    and user.is_admin
                                    and token_version_matches_user(payload, user)
                                ):
                                    is_admin = True
                    except Exception as e:
                        logger.error(f"Error verifying admin bypass: {e}")

                if not is_admin:
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": "System is undergoing maintenance. Only administrators can access."
                        },
                    )

        # 3. IP Filtering
        filters = db.query(IPFilter).all()
        for f in filters:
            if (
                f.rule_type == "specific_ip"
                and f.filter_type == "blacklist"
                and f.value == client_ip
            ):
                return JSONResponse(
                    status_code=403, content={"detail": "Your IP has been blacklisted."}
                )
            # (Country blocking would require geoip database, skipped for simple implementation but model supports it)

        response = await call_next(request)

        # 5. Sliding Session (Reset timer on activity)
        if (
            sys_settings
            and sys_settings.session_reset_on_activity
            and request.url.path != "/auth/logout"
        ):
            auth_header = request.headers.get("Authorization")
            cookie_token = request.cookies.get("access_token")
            token = None
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            elif cookie_token:
                token = cookie_token

            if token:
                try:
                    from datetime import timedelta

                    from app.utils.auth import (
                        create_access_token,
                        decode_token,
                        token_version_matches_user,
                    )

                    payload = decode_token(token)
                    if payload:
                        u_id = payload.get("sub")
                        if u_id:
                            from app.models.db import User

                            user = db.query(User).filter(User.id == int(u_id)).first()
                            if not user or not token_version_matches_user(payload, user):
                                return response

                            # Re-issue token with full duration
                            expire_minutes = 30  # default
                            if sys_settings.session_length:
                                length = sys_settings.session_length
                                unit = sys_settings.session_unit or "hours"
                                if unit == "hours":
                                    expire_minutes = length * 60
                                elif unit == "days":
                                    expire_minutes = length * 1440

                            new_token = create_access_token(
                                data={"sub": str(u_id), "tv": int(user.token_version or 0)},
                                expires_delta=timedelta(minutes=expire_minutes),
                            )
                            response.headers["X-New-Token"] = new_token
                            response.headers["Access-Control-Expose-Headers"] = "X-New-Token"
                            response.set_cookie(
                                key="access_token",
                                value=new_token,
                                httponly=True,
                                secure=settings.COOKIE_SECURE,
                                samesite=settings.COOKIE_SAMESITE,
                                max_age=expire_minutes * 60,
                                path="/",
                            )

                            # Also refresh CSRF token cookie to keep it in sync
                            csrf_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
                            if csrf_token:
                                response.set_cookie(
                                    key=settings.CSRF_COOKIE_NAME,
                                    value=csrf_token,
                                    httponly=False,  # Must be False for JS to read
                                    secure=settings.COOKIE_SECURE,
                                    samesite=settings.COOKIE_SAMESITE,
                                    max_age=expire_minutes * 60,
                                    path="/",
                                )
                except Exception:
                    pass  # Silently fail for token re-issue

        return response
    finally:
        db.close()


# Include routers
app.include_router(auth.router)
app.include_router(subjects.router)
app.include_router(resources.router)
app.include_router(notes.router)
app.include_router(chat.router)
app.include_router(logs.router)

app.include_router(study_sessions.router)
app.include_router(search.router)
app.include_router(analytics.router)
app.include_router(processing.router)
app.include_router(groups.router)
app.include_router(snapshots.router)
app.include_router(templates.router)
app.include_router(prompts.router)
app.include_router(admin.router)
app.include_router(support.router)
app.include_router(ws.router)
app.include_router(exercises.router)
app.include_router(voice.router)



@app.get("/http-cat/{status_code}")
async def http_cat_proxy(status_code: int):
    """Proxy to http.cat images (404, 500, etc.)"""
    import httpx

    url = f"https://http.cat/{status_code}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        from starlette.responses import Response

        return Response(
            content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg")
        )


@app.get("/health")
def health_check():
    """Health check endpoint — distinguishes API vs DB status."""
    from sqlalchemy import text

    from app.utils.db import SessionLocal

    db_ok = False
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db.commit()
        db_ok = True
    except Exception:
        db_ok = False
    finally:
        db.close()

    if db_ok:
        return {"status": "healthy", "api": "ok", "database": "ok"}
    return {"status": "degraded", "api": "ok", "database": "down"}


@app.get("/docs")
def docs():
    """OpenAPI documentation"""
    return {"message": "API documentation available at /docs"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.API_PORT, reload=settings.DEBUG)
