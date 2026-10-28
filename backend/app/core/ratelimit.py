import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import RateLimited

_hits: dict[str, deque] = defaultdict(deque)


def _check(key: str, limit: int, window: float = 60.0) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise RateLimited("Too many requests, slow down", details={"retry_after_s": int(window - (now - q[0])) + 1})
    q.append(now)


def reset() -> None:
    _hits.clear()


def auth_limiter(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    _check(f"auth:{ip}", get_settings().rate_limit_auth_per_min)


def upload_limiter(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    _check(f"upload:{ip}", get_settings().rate_limit_upload_per_min)
