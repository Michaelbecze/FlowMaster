"""Site staleness detection: an active->stale transition is detected here (from the
event stream Realtime already consumes) and pushed to Identity as the system of record
for Site.status, plus emitted as a site_status_changed message (FR-004)."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)

SiteStatusListener = Callable[[str, str], Awaitable[None]]

_last_seen: dict[str, float] = {}
_last_reported_status: dict[str, str] = {}
_IDENTITY_SEEN_THROTTLE_SECONDS = 5.0
_last_identity_call: dict[str, float] = {}


async def note_site_seen(site_id: str) -> None:
    now = time.time()
    _last_seen[site_id] = now

    if _last_reported_status.get(site_id) == "stale":
        _last_reported_status[site_id] = "active"
        await _set_status(site_id, "active")

    last_call = _last_identity_call.get(site_id, 0.0)
    if now - last_call >= _IDENTITY_SEEN_THROTTLE_SECONDS:
        _last_identity_call[site_id] = now
        await _report_seen(site_id)


async def _report_seen(site_id: str) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=3.0) as client:
        try:
            await client.post(
                f"/internal/sites/{site_id}/seen",
                json={"seen_at": datetime.now(timezone.utc).isoformat()},
            )
        except httpx.HTTPError:
            logger.warning("identity unreachable while reporting site %s seen", site_id)


async def _set_status(site_id: str, status: str) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=3.0) as client:
        try:
            await client.post(f"/internal/sites/{site_id}/status", json={"status": status})
        except httpx.HTTPError:
            logger.warning("identity unreachable while setting site %s status", site_id)


async def run_staleness_sweep(on_status_changed: SiteStatusListener) -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.staleness_sweep_interval_seconds)
        now = time.time()
        for site_id, last_seen in list(_last_seen.items()):
            is_stale = now - last_seen > settings.stale_after_seconds
            previous = _last_reported_status.get(site_id, "active")
            if is_stale and previous != "stale":
                _last_reported_status[site_id] = "stale"
                await _set_status(site_id, "stale")
                await on_status_changed(site_id, "stale")
