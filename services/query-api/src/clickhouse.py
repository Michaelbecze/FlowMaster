"""Shared async ClickHouse client for the query routes."""

from __future__ import annotations

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from .config import get_settings

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await clickhouse_connect.get_async_client(dsn=get_settings().clickhouse_url)
    return _client
