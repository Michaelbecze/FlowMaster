"""Ingestion service entry point: starts the UDP NetFlow v5 listener alongside a small
FastAPI app exposing health and ingest metrics (FR-014)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import configure_logging

from .listener import start_listener
from .metrics import metrics
from .producer import close_producer

configure_logging("ingestion")


@asynccontextmanager
async def lifespan(app: FastAPI):
    transport = await start_listener()
    try:
        yield
    finally:
        transport.close()
        await close_producer()


app = FastAPI(title="FlowMaster Ingestion Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics_endpoint() -> dict[str, int]:
    return metrics.as_dict()
