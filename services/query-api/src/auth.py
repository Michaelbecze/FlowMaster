"""Auth dependency for query-api routes.

Per contracts/gateway-routing.md, the Gateway has already validated the bearer token
before proxying here, so query-api does not duplicate that validation — it only
requires the header to still be present (defense against a route being reached any
other way). Full per-user site-scope enforcement (FR-009) is User Story 3's shared
authz dependency (tasks.md T078); every endpoint here still enforces site scope
server-side by construction (never trusting a client-supplied ``sites`` filter as
authorization) against the org-wide default described in services/realtime/src/websocket.py.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status


async def require_authenticated(authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return authorization
