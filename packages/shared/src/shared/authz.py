"""Shared server-side site-scope authorization dependency, used by query-api and
alerting so neither service ever trusts a client-supplied site filter as authorization
(contracts/query-api.md) — FR-009's enforcement lives here once, not duplicated per
service.

Resolves the caller against identity's GET /auth/whoami (the single point of truth
for both token validity and site scope, per contracts/identity-api.md), so this is one
network round trip per request, not a re-implementation of session/token validation.
"""

from __future__ import annotations

import os

import httpx
from fastapi import Header, HTTPException, status
from pydantic import BaseModel


class Principal(BaseModel):
    user_id: str
    email: str
    all_sites: bool
    site_ids: list[str]

    def is_allowed(self, site_id: str) -> bool:
        return self.all_sites or site_id in self.site_ids

    def filter_sites(self, requested: list[str]) -> list[str]:
        if self.all_sites:
            return requested
        return [s for s in requested if s in self.site_ids]


async def require_site_scope(authorization: str | None = Header(None)) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    identity_base_url = os.environ.get("IDENTITY_BASE_URL", "http://identity:8001")
    async with httpx.AsyncClient(base_url=identity_base_url, timeout=3.0) as client:
        try:
            resp = await client.get("/auth/whoami", headers={"authorization": authorization})
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Identity service unavailable") from exc

    if resp.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials")

    return Principal(**resp.json())
