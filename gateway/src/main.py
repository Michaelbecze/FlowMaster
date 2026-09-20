"""Gateway entry point: single network-facing entry for the frontend and external
integrators (contracts/gateway-routing.md). Terminates auth + rate limiting, then
reverse-proxies to the owning backend service."""

from __future__ import annotations

import asyncio

import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import Response
from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from shared.logging import configure_logging

from .config import get_settings
from .middleware.auth import AuthMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .routing import resolve_route

configure_logging("gateway")

app = FastAPI(title="FlowMaster Gateway")
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route(
    "/api/v1/{path:path}",
    methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
)
async def proxy(path: str, request: Request) -> Response:
    route = resolve_route(request.url.path)
    if route is None:
        return Response(status_code=404)

    settings = get_settings()
    base_url = getattr(settings, route.upstream_base_url_setting)
    upstream_path = request.url.path.removeprefix(route.prefix)

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        upstream_response = await client.request(
            request.method,
            upstream_path,
            params=request.query_params,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            content=await request.body(),
        )
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers={
            k: v
            for k, v in upstream_response.headers.items()
            if k.lower() not in ("content-encoding", "transfer-encoding")
        },
    )


@app.websocket("/api/v1/realtime")
async def realtime_proxy(websocket: WebSocket) -> None:
    """Proxies the realtime WebSocket channel (contracts/realtime-channel.md); auth is
    validated at upgrade time before any frame is forwarded.

    Browsers' native WebSocket API cannot set an Authorization header, so the session
    token is accepted as a `token` query parameter here as well — the same credential,
    just carried the way a browser can actually send it on this one route.
    """
    authorization = websocket.headers.get("authorization")
    if not authorization:
        token = websocket.query_params.get("token")
        authorization = f"Bearer {token}" if token else None
    if not authorization:
        await websocket.close(code=4401)
        return

    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.identity_base_url, timeout=5.0) as client:
        auth_check = await client.get("/auth/whoami", headers={"authorization": authorization})
    if auth_check.status_code != 200:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    upstream_url = (
        settings.realtime_base_url.replace("http://", "ws://").replace("https://", "wss://")
        + "/ws"
    )

    async with websockets.connect(upstream_url) as upstream:

        async def client_to_upstream() -> None:
            try:
                async for message in websocket.iter_text():
                    await upstream.send(message)
            except (WebSocketDisconnect, ConnectionClosed):
                pass

        async def upstream_to_client() -> None:
            try:
                async for message in upstream:
                    await websocket.send_text(message)
            except ConnectionClosed:
                pass

        done, pending = await asyncio.wait(
            [
                asyncio.create_task(client_to_upstream()),
                asyncio.create_task(upstream_to_client()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
