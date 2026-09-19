"""GET /sites/status — per-site connectivity status and last_seen_at (FR-004), scoped
to the caller's authorized sites (FR-009)."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from shared.api.envelope import Envelope
from shared.authz import Principal, require_site_scope

from ..config import get_settings

router = APIRouter(tags=["query"])


@router.get("/sites/status")
async def get_sites_status(
    principal: Principal = Depends(require_site_scope),
) -> Envelope[list[dict]]:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=3.0) as client:
        resp = await client.get("/internal/sites")
        resp.raise_for_status()
        sites = resp.json()

    data = [
        {"site_id": s["id"], "status": s["status"], "last_seen_at": s["last_seen_at"]}
        for s in sites
        if principal.is_allowed(s["id"])
    ]
    return Envelope.of(data, empty=len(data) == 0)
