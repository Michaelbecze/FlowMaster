"""Reads the organization's retention window from identity over the private network
(never identity's database directly — constitution Principle I)."""

from __future__ import annotations

import httpx

from .config import get_settings


async def get_retention_days() -> int:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=3.0) as client:
        try:
            resp = await client.get("/internal/retention-policy")
            resp.raise_for_status()
            return resp.json()["duration_days"]
        except httpx.HTTPError:
            return 1
