"""Reads Site status from identity over the private network (never identity's
database directly — constitution Principle I)."""

from __future__ import annotations

import httpx

from .config import get_settings


async def list_site_statuses() -> dict[str, str]:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=3.0) as client:
        try:
            resp = await client.get("/internal/sites")
            resp.raise_for_status()
        except httpx.HTTPError:
            return {}
    return {row["id"]: row["status"] for row in resp.json()}
