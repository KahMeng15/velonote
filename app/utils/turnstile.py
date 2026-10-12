"""Cloudflare Turnstile server-side validation"""

import json
import logging

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

_TURNSTILE_PATHS = frozenset(
    {
        "/auth/login",
        "/auth/register",
        "/auth/google-login",
        "/auth/google-complete",
        "/auth/password-reset-request",
        "/auth/password-reset",
        "/auth/resend-verification",
    }
)


async def validate_turnstile(token: str, ip: str | None = None) -> bool:
    """Validate a Turnstile token against Cloudflare's verification endpoint."""
    settings = get_settings()
    if not settings.TURNSTILE_SECRET_KEY:
        logger.warning("TURNSTILE_SECRET_KEY not set — skipping validation")
        return True

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                VERIFY_URL,
                data={
                    "secret": settings.TURNSTILE_SECRET_KEY,
                    "response": token,
                    "remoteip": ip or "",
                },
                timeout=10,
            )
            result = resp.json()
            success = result.get("success", False)
            if not success:
                error_codes = result.get("error-codes", [])
                logger.warning("Turnstile validation failed: error_codes=%s ip=%s", error_codes, ip)
            return success
    except httpx.ConnectError:
        logger.error("Turnstile verification failed: cannot reach Cloudflare (network error)")
        # Fail open in dev, fail closed in prod
        settings = get_settings()
        if settings.ENVIRONMENT.lower() != "production":
            return True
        return False
    except Exception as e:
        logger.warning("Turnstile verification error: %s", e)
        return False


async def turnstile_middleware(request: Request, call_next):
    """Middleware that validates Turnstile tokens on public auth endpoints."""
    if request.method != "POST":
        return await call_next(request)

    if request.url.path not in _TURNSTILE_PATHS:
        return await call_next(request)

    settings = get_settings()
    if not settings.TURNSTILE_SECRET_KEY:
        return await call_next(request)

    body = await request.body()
    if not body:
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing request body for Turnstile verification"},
        )

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid JSON body for Turnstile verification"},
        )

    token = data.get("cf_turnstile_response")
    if not token:
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing Turnstile verification token"},
        )

    ip = request.client.host if request.client else None
    valid = await validate_turnstile(token, ip)
    if not valid:
        return JSONResponse(
            status_code=400,
            content={"detail": "Turnstile verification failed. Please try again."},
        )

    return await call_next(request)
