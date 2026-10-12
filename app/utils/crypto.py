"""Cryptographic helpers for encrypting sensitive settings at rest."""

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

_ENCRYPTED_PREFIX = "enc:"


@lru_cache(maxsize=1)
def _get_cipher() -> Fernet | None:
    """Return a Fernet cipher instance when APP_ENCRYPTION_KEY is configured."""
    settings = get_settings()
    key = (settings.APP_ENCRYPTION_KEY or "").strip()
    if not key:
        return None

    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        logger.error("Invalid APP_ENCRYPTION_KEY; encryption disabled", extra={"error": str(exc)})
        return None


def is_encrypted_value(value: str | None) -> bool:
    return bool(value and value.startswith(_ENCRYPTED_PREFIX))


def encrypt_secret(value: str | None) -> str | None:
    """Encrypt a value when crypto is configured; otherwise return original value."""
    if not value:
        return value

    if is_encrypted_value(value):
        return value

    cipher = _get_cipher()
    if not cipher:
        return value

    token = cipher.encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_ENCRYPTED_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str | None:
    """Decrypt a value if it is encrypted and crypto is configured."""
    if not value:
        return value

    if not is_encrypted_value(value):
        return value

    cipher = _get_cipher()
    if not cipher:
        return value

    token = value[len(_ENCRYPTED_PREFIX) :]
    try:
        return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("Unable to decrypt secret value with configured APP_ENCRYPTION_KEY")
        return None
    except Exception as exc:
        logger.error("Unexpected error decrypting secret", extra={"error": str(exc)})
        return None
