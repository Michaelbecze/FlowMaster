"""Realtime service entry point: consumes flow-records.v1 into the Redis aggregate
cache, sweeps for stale sites, and serves the /ws push channel."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket

from shared.logging import configure_logging

from .aggregator import run_aggregator
from .staleness import run_staleness_sweep
from .websocket import broadcast_site_status_changed, websocket_endpoint

configure_logging("realtime")


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = await run_aggregator()
    sweep_task = asyncio.create_task(run_staleness_sweep(broadcast_site_status_changed))
    try:
        yield
    finally:
        sweep_task.cancel()
        await consumer.stop()


app = FastAPI(title="FlowMaster Realtime Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket_endpoint(websocket)
