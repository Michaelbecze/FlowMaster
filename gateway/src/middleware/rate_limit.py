"""Redis-backed per-token rate limiting (FR-019). Applied once at the Gateway rather
than duplicated per service (contracts/gateway-routing.md)."""

from __future__ import annotations

import time

import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ..config import get_settings

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        identity = _client_identity(request)
        window = int(time.time() // 60)
        key = f"ratelimit:{identity}:{window}"

        client = _get_redis()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 60)

        settings = get_settings()
        if count > settings.rate_limit_per_minute:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

        return await call_next(request)


def _client_identity(request: Request) -> str:
    authorization = request.headers.get("authorization")
    if authorization:
        return authorization
    client = request.client
    return client.host if client else "unknown"
