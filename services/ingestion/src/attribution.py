"""Site attribution: network_identity (exporter source IP) -> site_id.

Calls identity's internal service-to-service endpoint over the private network rather
than reading identity's database directly (constitution Principle I). Results are
cached in-process; an unattributed exporter is counted, not silently dropped.
"""

from __future__ import annotations

import time

import httpx

from .config import get_settings
from .metrics import metrics

_CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[str | None, float]] = {}


async def attribute_site(network_identity: str) -> str | None:
    cached = _cache.get(network_identity)
    now = time.monotonic()
    if cached is not None and now - cached[1] < _CACHE_TTL_SECONDS:
        return cached[0]

    settings = get_settings()
    site_id: str | None = None
    async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=3.0) as client:
        try:
            resp = await client.get(f"/internal/sites/by-network-identity/{network_identity}")
            if resp.status_code == 200:
                site_id = resp.json().get("site_id")
        except httpx.HTTPError:
            # Identity is momentarily unreachable — attribute nothing rather than block
            # ingest (constitution Principle IV: Ingestion must never block downstream).
            site_id = None

    _cache[network_identity] = (site_id, now)
    if site_id is None:
        metrics.record_unattributed()
    return site_id
