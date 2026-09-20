"""Bearer-token validation middleware.

Validates every non-public request against the Identity service before routing, so
backend services never need to duplicate auth logic (contracts/gateway-routing.md).
Public paths (e.g. /auth/login) bypass validation but still route through the Gateway.
"""

from __future__ import annotations

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ..config import get_settings
from ..routing import is_public


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/v1/") or is_public(request.url.path):
            return await call_next(request)

        authorization = request.headers.get("authorization")
        if not authorization:
            return JSONResponse({"detail": "Missing Authorization header"}, status_code=401)

        settings = get_settings()
        async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=5.0) as client:
            try:
                resp = await client.get(
                    "/auth/whoami", headers={"authorization": authorization}
                )
            except httpx.HTTPError:
                return JSONResponse({"detail": "Identity service unavailable"}, status_code=503)

        if resp.status_code != 200:
            return JSONResponse({"detail": "Invalid or expired credentials"}, status_code=401)

        request.state.user = resp.json()
        return await call_next(request)
