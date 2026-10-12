"""Thread-safe in-memory TTL cache replacing Redis."""

import fnmatch
import hashlib
import json
import logging
import time
from collections.abc import Callable
from functools import wraps
from threading import Lock
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class InMemoryTTLCache:
    """Thread-safe in-memory cache with Time-To-Live (TTL) expiration support."""

    def __init__(self, max_items: int = 10000):
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = Lock()
        self._max_items = max_items

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, json_data = entry
            if expires_at == 0 or expires_at > now:
                try:
                    return json.loads(json_data)
                except Exception as e:
                    logger.error(f"Failed to deserialize cache key {key}: {e}")
                    return None
            # Expired
            self._store.pop(key, None)
            return None

    def set(self, key: str, value: Any, ttl: int | None = None):
        now = time.time()
        expires_at = (now + ttl) if ttl and ttl > 0 else 0
        try:
            serializable_value = jsonable_encoder(value)
            json_data = json.dumps(serializable_value)
        except Exception as e:
            logger.error(f"Failed to serialize cache value for key {key}: {e}")
            return

        with self._lock:
            if len(self._store) >= self._max_items:
                self._prune_expired(now)
                # If still over max limit, remove oldest item
                if len(self._store) >= self._max_items:
                    oldest_key = next(iter(self._store))
                    self._store.pop(oldest_key, None)
            self._store[key] = (expires_at, json_data)

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def clear_pattern(self, pattern: str):
        with self._lock:
            matched_keys = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
            for k in matched_keys:
                self._store.pop(k, None)
            if matched_keys:
                logger.debug(f"Cleared {len(matched_keys)} cache keys matching pattern: {pattern}")

    def _prune_expired(self, now: float):
        expired = [k for k, (exp, _) in self._store.items() if exp != 0 and exp <= now]
        for k in expired:
            self._store.pop(k, None)


# Global cache instance
_memory_cache = InMemoryTTLCache()


# --- Async Cache API ---


async def get_cache_async(key: str) -> Any | None:
    """Get a value from cache asynchronously."""
    return _memory_cache.get(key)


async def set_cache_async(key: str, value: Any, ttl: int | None = None):
    """Set a value in cache asynchronously."""
    if ttl is None:
        ttl = settings.CACHE_TTL_SECONDS
    _memory_cache.set(key, value, ttl=ttl)


async def delete_cache_async(key: str):
    """Delete a value from cache asynchronously."""
    _memory_cache.delete(key)


# --- Sync Cache API ---


def get_cache_sync(key: str) -> Any | None:
    """Get a value from cache synchronously."""
    return _memory_cache.get(key)


def set_cache_sync(key: str, value: Any, ttl: int | None = None):
    """Set a value in cache synchronously."""
    if ttl is None:
        ttl = settings.CACHE_TTL_SECONDS
    _memory_cache.set(key, value, ttl=ttl)


def delete_cache_sync(key: str):
    """Delete a value from cache synchronously."""
    _memory_cache.delete(key)


def clear_cache_pattern_sync(pattern: str):
    """Delete all keys matching a pattern synchronously."""
    _memory_cache.clear_pattern(pattern)


# --- Backward Compatibility Stubs ---


async def get_redis_async() -> None:
    """Stub for backward compatibility. In-memory cache is used."""
    return None


def get_redis_sync() -> None:
    """Stub for backward compatibility. In-memory cache is used."""
    return None


# --- Cache Response Decorator ---


def cache_response(ttl: int | None = None, user_specific: bool = True):
    """
    Decorator to cache FastAPI response (async).
    :param ttl: Cache TTL in seconds.
    :param user_specific: If True, includes current_user.id in the cache key.
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request | None = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                return await func(*args, **kwargs)

            # Base key from URL
            cache_key = f"cache_resp:{request.url.path}:{request.query_params!s}"

            # Add user context if required
            if user_specific:
                current_user = kwargs.get("current_user")
                if current_user and hasattr(current_user, "id"):
                    cache_key = f"{cache_key}:u{current_user.id}"
                else:
                    auth = request.headers.get("Authorization", "")
                    if auth:
                        auth_hash = hashlib.sha256(auth.encode()).hexdigest()
                        cache_key = f"{cache_key}:auth{auth_hash}"

            cached_val = await get_cache_async(cache_key)
            if cached_val is not None:
                logger.info(f"Cache hit for {cache_key}")
                return cached_val

            result = await func(*args, **kwargs)
            if result is not None:
                await set_cache_async(cache_key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
