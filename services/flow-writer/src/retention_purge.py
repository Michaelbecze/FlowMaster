"""Retention purge job — runs on its own schedule, independent of ingest/query
(constitution Principle IV), keeping ClickHouse's declared TTL in sync with the
organization's configured RetentionPolicy.duration_days (FR-005).

A declared TTL is a scheduled ClickHouse background merge, not an ad hoc DELETE loop,
so it never blocks the Query API or the realtime path.
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from .batch_writer import get_client
from .config import get_settings

logger = logging.getLogger(__name__)


async def _current_retention_days(pool: asyncpg.Pool, default_days: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT duration_days FROM retention_policy LIMIT 1")
    return row["duration_days"] if row else default_days


async def apply_retention_ttl(pool: asyncpg.Pool) -> int:
    settings = get_settings()
    days = await _current_retention_days(pool, settings.default_retention_days)
    client = await get_client()
    await client.command(
        f"ALTER TABLE flow_record MODIFY TTL toDateTime(timestamp) + INTERVAL {int(days)} DAY"
    )
    logger.info("retention TTL synced to %d day(s)", days)
    return days


async def run_retention_purge_loop() -> None:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    try:
        while True:
            try:
                await apply_retention_ttl(pool)
            except Exception:  # noqa: BLE001 — a purge-loop failure must not crash the service
                logger.exception("retention purge iteration failed; will retry next interval")
            await asyncio.sleep(settings.retention_check_interval_seconds)
    finally:
        await pool.close()
