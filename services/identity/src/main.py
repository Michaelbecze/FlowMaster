"""Identity service entry point.

Users, roles, sites, auth (session + API tokens), and the audit log — the single point of
truth every other service trusts for the site-scope claim (contracts/identity-api.md).
"""

from __future__ import annotations

from fastapi import FastAPI

from shared.logging import configure_logging

from .auth.api_tokens import router as api_tokens_router
from .auth.session import router as session_router
from .db import close_pool
from .sites.router import internal_router as sites_internal_router
from .sites.router import router as sites_router

configure_logging("identity")

app = FastAPI(title="FlowMaster Identity Service")
app.include_router(session_router)
app.include_router(api_tokens_router)
app.include_router(sites_router)
app.include_router(sites_internal_router)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await close_pool()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
