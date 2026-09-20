"""Batches FlowRecordEvent rows into ClickHouse so ingest volume does not degrade
query latency (constitution Principle IV)."""

from __future__ import annotations

import asyncio
import logging

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from shared.events.flow_record import FlowRecordEvent

from .config import get_settings

logger = logging.getLogger(__name__)

COLUMNS = [
    "timestamp",
    "site_id",
    "src_addr",
    "dst_addr",
    "src_port",
    "dst_port",
    "protocol",
    "application",
    "bytes",
    "packets",
    "direction",
    "ingested_at",
]

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await clickhouse_connect.get_async_client(dsn=get_settings().clickhouse_url)
    return _client


def _row(event: FlowRecordEvent) -> list:
    return [
        event.observed_at,
        event.site_id,
        event.src_addr,
        event.dst_addr,
        event.src_port,
        event.dst_port,
        event.protocol,
        event.application,
        event.bytes,
        event.packets,
        event.direction.value,
        event.ingested_at,
    ]


class BatchWriter:
    """Buffers events in-process and flushes on size or time, whichever comes first."""

    def __init__(self) -> None:
        settings = get_settings()
        self._max_size = settings.batch_max_size
        self._max_seconds = settings.batch_max_seconds
        self._buffer: list[FlowRecordEvent] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None

    async def add(self, event: FlowRecordEvent) -> None:
        async with self._lock:
            self._buffer.append(event)
            should_flush = len(self._buffer) >= self._max_size
            if self._flush_task is None:
                self._flush_task = asyncio.create_task(self._flush_after_delay())
        if should_flush:
            await self.flush()

    async def _flush_after_delay(self) -> None:
        await asyncio.sleep(self._max_seconds)
        await self.flush()

    async def flush(self) -> int:
        async with self._lock:
            batch, self._buffer = self._buffer, []
            # _flush_after_delay() calls flush() on itself once its sleep elapses — cancelling
            # self._flush_task unconditionally would cancel the currently-running task at its
            # very next await (the insert below), silently discarding the batch. Only cancel a
            # *pending* timer task, never the one already executing this flush.
            current_task = asyncio.current_task()
            if self._flush_task is not None and self._flush_task is not current_task:
                self._flush_task.cancel()
            self._flush_task = None
        if not batch:
            return 0

        client = await get_client()
        await client.insert("flow_record", [_row(e) for e in batch], column_names=COLUMNS)
        logger.info("flushed %d flow records to ClickHouse", len(batch))
        return len(batch)
