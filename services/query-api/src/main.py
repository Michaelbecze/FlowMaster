"""Query API entry point: dashboard summary, drill-down, and historical query
endpoints (contracts/query-api.md)."""

from __future__ import annotations

from fastapi import FastAPI

from shared.logging import configure_logging

from .db import close_pool
from .routes.flow_map import router as flow_map_router
from .routes.flows import router as flows_router
from .routes.internal_flows import router as internal_flows_router
from .routes.reports import router as reports_router
from .routes.site_status import router as site_status_router
from .routes.summary import router as summary_router
from .routes.top_talkers import router as top_talkers_router
from .routes.traffic_over_time import router as traffic_over_time_router

configure_logging("query-api")

app = FastAPI(title="FlowMaster Query API")
app.include_router(summary_router)
app.include_router(top_talkers_router)
app.include_router(site_status_router)
app.include_router(flows_router)
app.include_router(reports_router)
app.include_router(internal_flows_router)
app.include_router(traffic_over_time_router)
app.include_router(flow_map_router)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await close_pool()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
