"""The /ws endpoint per contracts/realtime-channel.md: scope-filtered subscription,
stats_update push >=1/5s, immediate push on reconnect.

Fine-grained site-scope enforcement (which sites a given user may subscribe to) is
User Story 3's shared authz dependency (tasks.md T078); until that lands, every
authenticated caller (the Gateway has already validated the bearer token before
proxying here) is treated as org-wide scope, matching the default UserRoleAssignment
row (site_id NULL = org-wide) a fresh v1 organization starts with.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from .aggregator import get_site_summary, known_site_ids
from .config import get_settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}

    def register(self, websocket: WebSocket, sites: set[str]) -> None:
        self._connections[websocket] = sites

    def unregister(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    def connections_for_site(self, site_id: str) -> list[WebSocket]:
        return [ws for ws, sites in self._connections.items() if site_id in sites]

    def all_connections(self) -> list[tuple[WebSocket, set[str]]]:
        return list(self._connections.items())


manager = ConnectionManager()


async def _send_stats_update(websocket: WebSocket, sites: set[str]) -> None:
    summaries = [await get_site_summary(site_id) for site_id in sites]
    total_bytes = sum(s["total_bytes"] for s in summaries)
    protocol_mix: dict[str, int] = {}
    top_talkers: list[dict] = []
    for s in summaries:
        for app, b in s["protocol_mix"].items():
            protocol_mix[app] = protocol_mix.get(app, 0) + b
        top_talkers.extend(s["top_talkers"])
    top_talkers.sort(key=lambda t: t["bytes"], reverse=True)

    await websocket.send_json(
        {
            "type": "stats_update",
            "sites": list(sites),
            "window": "5m",
            "summary": {
                "total_bytes": total_bytes,
                "protocol_mix": protocol_mix,
                "top_talkers": top_talkers[:10],
            },
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
    )


async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        subscribe_msg = await websocket.receive_json()
    except Exception:
        await websocket.close(code=4400)
        return

    requested = set(subscribe_msg.get("sites", []))
    known = await known_site_ids()
    # Silent-drop of out-of-scope/unknown sites rather than erroring (contract §Connection).
    sites = requested & known if requested else known
    manager.register(websocket, sites)

    await _send_stats_update(websocket, sites)  # immediate push on connect/reconnect

    settings = get_settings()
    try:
        while True:
            await asyncio.sleep(settings.push_interval_seconds)
            await _send_stats_update(websocket, sites)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(websocket)


async def broadcast_site_status_changed(site_id: str, status: str) -> None:
    payload = json.dumps(
        {
            "type": "site_status_changed",
            "site_id": site_id,
            "status": status,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    for websocket in manager.connections_for_site(site_id):
        try:
            await websocket.send_text(payload)
        except Exception:
            logger.warning("failed to push site_status_changed to a disconnected client")
