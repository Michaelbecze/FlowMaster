"""Reads a rule owner's *current* site scope from identity over the private network
(never identity's database directly — constitution Principle I). Used by the
evaluator, which runs as a background job with no caller bearer token, so it cannot
use shared.authz's GET /auth/whoami path."""

from __future__ import annotations

import httpx

from .config import get_settings


async def get_owner_scope(user_id: str) -> tuple[bool, list[str]]:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=3.0) as client:
        try:
            resp = await client.get(f"/internal/sites/scope/{user_id}")
            resp.raise_for_status()
            data = resp.json()
            return data["all_sites"], data["site_ids"]
        except httpx.HTTPError:
            return False, []
