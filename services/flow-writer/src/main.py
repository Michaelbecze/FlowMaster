"""Flow-Writer entry point: consumes flow-records.v1, batches into ClickHouse, and
runs the retention purge loop independently of ingest/query."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import configure_logging

from .batch_writer import BatchWriter
from .consumer import run_consumer
from .retention_purge import run_retention_purge_loop

configure_logging("flow-writer")

writer = BatchWriter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = await run_consumer(writer)
    purge_task = asyncio.create_task(run_retention_purge_loop())
    try:
        yield
    finally:
        purge_task.cancel()
        await consumer.stop()
        await writer.flush()


app = FastAPI(title="FlowMaster Flow-Writer Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
