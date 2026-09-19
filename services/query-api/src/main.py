"""Query API entry point: dashboard summary, drill-down, and historical query
endpoints (contracts/query-api.md)."""

from __future__ import annotations

from fastapi import FastAPI

from shared.logging import configure_logging

from .routes.flows import router as flows_router
from .routes.site_status import router as site_status_router
from .routes.summary import router as summary_router
from .routes.top_talkers import router as top_talkers_router

configure_logging("query-api")

app = FastAPI(title="FlowMaster Query API")
app.include_router(summary_router)
app.include_router(top_talkers_router)
app.include_router(site_status_router)
app.include_router(flows_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
