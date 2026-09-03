"""API keys and a small in-memory rate limiter.

The limiter is per-process. If you run several API workers or replicas, put a real
limiter (nginx, Cloudflare, an API gateway) in front instead of relying on this.
"""

from __future__ import annotations

import hmac
import re
import threading
import time
from collections import deque

from fastapi import Request

from ..config import Settings
from .errors import APIError

_UNITS = {
    "second": 1.0,
    "sec": 1.0,
    "s": 1.0,
    "minute": 60.0,
    "min": 60.0,
    "m": 60.0,
    "hour": 3600.0,
    "h": 3600.0,
}
_SPEC = re.compile(r"^\s*(\d+)\s*/\s*(\d*)\s*([a-z]+)\s*$")


def parse_rate_limit(spec: str) -> tuple[int, float]:
    """``"30/minute"`` -> ``(30, 60.0)``; ``"100/5minute"`` -> ``(100, 300.0)``."""
    match = _SPEC.match(spec.lower())
    if not match or match.group(3) not in _UNITS:
        raise ValueError(f"invalid rate limit {spec!r}; expected e.g. '30/minute'")
    count = int(match.group(1))
    multiplier = int(match.group(2) or 1)
    return count, multiplier * _UNITS[match.group(3)]


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_prune = 0.0

    def check(self, key: str, now: float | None = None) -> float:
        """Record a hit for ``key``. Returns 0 if allowed, else seconds until the next slot."""
        now = time.monotonic() if now is None else now
        cutoff = now - self.window_s
        with self._lock:
            if now - self._last_prune > self.window_s:
                self._prune(cutoff)
                self._last_prune = now
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(0.0, hits[0] + self.window_s - now)
            hits.append(now)
            return 0.0

    def _prune(self, cutoff: float) -> None:
        stale = [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for k in stale:
            del self._hits[k]


def client_key(request: Request, settings: Settings) -> str:
    """The identity rate limits are keyed on: the client IP, or the proxy-reported one."""
    if settings.trust_proxy:
        if settings.client_ip_header:
            value = request.headers.get(settings.client_ip_header)
            if value:
                return value.strip()
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # The *last* hop is the one the proxy in front of us appended (or wrote, in
            # Caddy's case); earlier entries are whatever the client chose to send, so
            # keying on them would let a client rotate identities past the limit.
            return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "unknown"


async def require_api_key(request: Request) -> None:
    settings: Settings = request.app.state.settings
    if not settings.api_keys:
        return
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    token = token.strip()
    # compare_digest raises on non-ASCII strings; such a token is simply not a valid key.
    if (
        scheme.lower() == "bearer"
        and token.isascii()
        and any(key.isascii() and hmac.compare_digest(token, key) for key in settings.api_keys)
    ):
        return
    raise APIError(
        401,
        "unauthorized",
        "a valid API key is required: Authorization: Bearer <key>",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _retry_after(wait: float) -> int:
    return max(1, int(wait + 0.999))


async def enforce_rate_limit(request: Request) -> None:
    """Per-client limit first (so one abuser only hits their own bucket), then the global one."""
    settings: Settings = request.app.state.settings
    limiter: SlidingWindowLimiter | None = request.app.state.rate_limiter
    if limiter is not None:
        wait = limiter.check(client_key(request, settings))
        if wait > 0:
            retry = _retry_after(wait)
            raise APIError(
                429,
                "rate_limited",
                f"rate limit exceeded ({settings.rate_limit}); retry in {retry}s",
                headers={"Retry-After": str(retry)},
            )
    global_limiter: SlidingWindowLimiter | None = request.app.state.global_limiter
    if global_limiter is not None:
        wait = global_limiter.check("*")
        if wait > 0:
            retry = _retry_after(wait)
            raise APIError(
                429,
                "rate_limited",
                f"the service is at its global limit ({settings.global_rate_limit}); "
                f"retry in {retry}s",
                headers={"Retry-After": str(retry)},
            )
