"""Stage 5 security hardening: security headers and a login rate limiter."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

# Content Security Policy tuned to the dashboard's real dependencies:
# Leaflet from cdnjs and OpenStreetMap tiles. Same-origin API + WebSocket.
_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://*.openstreetmap.org "
    "https://server.arcgisonline.com https://*.arcgisonline.com "
    "https://cdnjs.cloudflare.com; "
    "script-src 'self' https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        # The dashboard is a build-free ES-module SPA: module imports carry no
        # cache-busting query, so without an explicit policy browsers heuristically
        # cache a module by its URL and never see new code. "no-cache" keeps the
        # cached copy but forces revalidation on every load, so StaticFiles returns
        # a cheap 304 when unchanged and fresh code immediately after a deploy.
        if not request.url.path.startswith("/api"):
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp


class RateLimiter:
    """Simple in-memory sliding-window limiter keyed by client IP.

    Suitable for single-instance brute-force protection on auth. For multi-instance
    deployments, move this to Redis.
    """

    def __init__(self, max_attempts: int, window_s: int) -> None:
        self.max = max_attempts
        self.window = window_s
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        dq = self._hits[key]
        while dq and now - dq[0] > self.window:
            dq.popleft()
        if len(dq) >= self.max:
            retry = int(self.window - (now - dq[0])) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"too many attempts; retry in {retry}s",
                headers={"Retry-After": str(retry)},
            )
        dq.append(now)


def client_ip(request: Request) -> str:
    # Honour a single proxy hop if present; otherwise the socket peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
