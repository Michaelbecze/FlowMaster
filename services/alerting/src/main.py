"""Alerting service entry point: rule CRUD, the flow-records.v1 volume-window
consumer, and the periodic evaluation loop (User Story 4)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import configure_logging

from .db import close_pool
from .evaluator import run_evaluation_loop, run_flow_consumer
from .routes.events import router as events_router
from .routes.rules import router as rules_router

configure_logging("alerting")


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = await run_flow_consumer()
    eval_task = asyncio.create_task(run_evaluation_loop())
    try:
        yield
    finally:
        eval_task.cancel()
        await consumer.stop()
        await close_pool()


app = FastAPI(title="FlowMaster Alerting Service", lifespan=lifespan)
app.include_router(rules_router)
app.include_router(events_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
