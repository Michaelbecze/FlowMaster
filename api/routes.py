import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

PROTO_NAMES = {
    1: "ICMP", 6: "TCP", 17: "UDP", 47: "GRE",
    50: "ESP", 58: "ICMPv6", 89: "OSPF", 132: "SCTP",
}

_FRONTEND = Path(__file__).parent.parent / "frontend" / "index.html"


class ConnectionManager:
    def __init__(self):
        self._clients: list[WebSocket] = []
        self.db = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)

    def disconnect(self, ws: WebSocket):
        self._clients.remove(ws)

    async def broadcast(self, payload: dict):
        data = json.dumps(payload)
        dead = []
        for ws in self._clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.remove(ws)

    async def broadcast_stats(self):
        if not self.db or not self._clients:
            return
        try:
            stats = await self.db.get_stats()
            await self.broadcast({"type": "stats", "data": stats})
        except Exception:
            logger.exception("WebSocket broadcast error")


manager = ConnectionManager()


def create_app(db) -> FastAPI:
    manager.db = db
    app = FastAPI(title="FlowMaster")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _FRONTEND.read_text()

    @app.get("/api/stats")
    async def stats(hours: float = 1.0):
        return await db.get_stats(hours)

    @app.get("/api/traffic-over-time")
    async def traffic_over_time(hours: float = 1.0):
        return await db.get_traffic_over_time(hours)

    @app.get("/api/top-talkers")
    async def top_talkers(limit: int = 10, hours: float = 1.0):
        return await db.get_top_talkers(limit, hours)

    @app.get("/api/top-destinations")
    async def top_destinations(limit: int = 10, hours: float = 1.0):
        return await db.get_top_destinations(limit, hours)

    @app.get("/api/protocols")
    async def protocols(hours: float = 1.0):
        rows = await db.get_protocols(hours)
        for r in rows:
            r["name"] = PROTO_NAMES.get(r["protocol"], f"Proto-{r['protocol']}")
        return rows

    @app.get("/api/applications")
    async def applications(hours: float = 1.0):
        return await db.get_applications(hours)

    @app.get("/api/recent-flows")
    async def recent_flows(limit: int = 50):
        return await db.get_recent_flows(limit)

    @app.get("/api/flows-at")
    async def flows_at(from_ts: float, to_ts: float, limit: int = 100):
        return await db.get_flows_in_range(from_ts, to_ts, limit)

    @app.get("/api/sankey")
    async def sankey(hours: float = 1.0):
        flows = await db.get_sankey_data(hours=hours)
        # Bipartite layout: separate source and destination nodes so the graph
        # is always a DAG even when an IP appears on both sides.
        src_ips = list({f["src_ip"] for f in flows})
        dst_ips = list({f["dst_ip"] for f in flows})
        nodes = [{"id": f"s:{ip}", "label": ip} for ip in src_ips] + \
                [{"id": f"d:{ip}", "label": ip} for ip in dst_ips]
        idx = {n["id"]: i for i, n in enumerate(nodes)}
        return {
            "nodes": nodes,
            "links": [
                {"source": idx[f"s:{f['src_ip']}"], "target": idx[f"d:{f['dst_ip']}"], "value": f["total_bytes"]}
                for f in flows
            ],
        }

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return app
