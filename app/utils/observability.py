"""Lightweight in-process runtime metrics.

These counters are intentionally simple and dependency-free. They provide
an immediate operational view for admins without requiring Prometheus.
"""

from collections import defaultdict
from threading import Lock
from time import time
from typing import Any

_started_at = time()
_lock = Lock()
_requests_total = 0
_errors_total = 0
_status_counts = defaultdict(int)
_path_counts = defaultdict(int)
_duration_ms_sum = 0


def record_request(path: str, status_code: int, duration_ms: int) -> None:
    global _requests_total, _errors_total, _duration_ms_sum
    with _lock:
        _requests_total += 1
        _duration_ms_sum += max(0, int(duration_ms))
        _status_counts[str(status_code)] += 1

        # Keep cardinality bounded by bucketizing dynamic paths.
        bucket = path
        if path.startswith("/note/"):
            bucket = "/note/{id}"
        elif path.startswith("/notes/"):
            bucket = "/notes/{id}"
        elif path.startswith("/chat/"):
            bucket = "/chat/*"

        _path_counts[bucket] += 1

        if status_code >= 500:
            _errors_total += 1


def get_runtime_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        avg_duration = (_duration_ms_sum / _requests_total) if _requests_total else 0.0
        uptime_seconds = int(time() - _started_at)
        return {
            "uptime_seconds": uptime_seconds,
            "requests_total": _requests_total,
            "errors_total": _errors_total,
            "avg_request_duration_ms": round(avg_duration, 2),
            "status_counts": dict(_status_counts),
            "top_paths": dict(
                sorted(_path_counts.items(), key=lambda item: item[1], reverse=True)[:20]
            ),
        }
