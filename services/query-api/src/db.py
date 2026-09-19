"""Async PostgreSQL connection pool for query-api's own tables (Report metadata —
plan.md: "PostgreSQL (reports metadata)"). Flow data itself lives only in ClickHouse."""

from __future__ import annotations

import asyncpg

from .config import get_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(get_settings().database_url, min_size=1, max_size=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
