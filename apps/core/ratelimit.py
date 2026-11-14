"""
Fixed-window rate limiting on the Django cache (Redis in production).
Shared across all API processes, unlike the frontend's in-memory limiter.
"""
from django.conf import settings
from django.core.cache import cache

from .errors import ApiError


def client_ip(request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "local")


def hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Count one hit. Returns (allowed, retry_after_seconds)."""
    full = f"rl:{key}"
    # add() is atomic: only the first hit in a window creates the key
    if cache.add(full, 1, timeout=window_seconds):
        return True, 0
    try:
        count = cache.incr(full)
    except ValueError:  # expired between add() and incr()
        cache.add(full, 1, timeout=window_seconds)
        return True, 0
    if count <= limit:
        return True, 0
    ttl = getattr(cache, "ttl", None)
    retry = ttl(full) if callable(ttl) else None
    return False, int(retry) if retry and retry > 0 else window_seconds


def enforce(key: str, limit: int, window_seconds: int, message: str):
    ok, retry = hit(key, limit, window_seconds)
    if not ok:
        raise ApiError(message.format(minutes=max(1, -(-retry // 60))), 429, {"retryAfter": retry})


def reset(key: str):
    cache.delete(f"rl:{key}")
