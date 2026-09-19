"""Shared ClickHouse flow-record query, used by both GET /flows (User Story 1) and
the Report endpoints (User Story 2) so a saved report's "current results" are computed
by the exact same query a live drill-down would run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import clickhouse, retention_client

PAGE_SIZE = 100

_COLUMNS = [
    "timestamp",
    "site_id",
    "src_addr",
    "dst_addr",
    "src_port",
    "dst_port",
    "protocol",
    "application",
    "bytes",
    "packets",
    "direction",
]


@dataclass(frozen=True)
class FlowFilter:
    start: datetime
    end: datetime
    site_id: str | None = None
    protocol: int | None = None
    application: str | None = None
    host: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "site_id": self.site_id,
            "protocol": self.protocol,
            "application": self.application,
            "host": self.host,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "FlowFilter":
        return cls(
            start=datetime.fromisoformat(str(data["start"])),
            end=datetime.fromisoformat(str(data["end"])),
            site_id=data.get("site_id"),  # type: ignore[arg-type]
            protocol=data.get("protocol"),  # type: ignore[arg-type]
            application=data.get("application"),  # type: ignore[arg-type]
            host=data.get("host"),  # type: ignore[arg-type]
        )


async def query_flows(
    flt: FlowFilter, page: int = 1, allowed_site_ids: list[str] | None = None
) -> list[dict]:
    """allowed_site_ids, when not None, restricts results to the caller's site scope
    (FR-009) even when flt.site_id is unset — the server-side enforcement callers get
    by resolving a Principal via shared.authz and passing principal.site_ids here when
    principal.all_sites is False."""
    conditions = ["timestamp >= {start:DateTime64}", "timestamp <= {end:DateTime64}"]
    params: dict[str, object] = {"start": flt.start, "end": flt.end}

    if flt.site_id:
        conditions.append("site_id = {site_id:String}")
        params["site_id"] = flt.site_id
    elif allowed_site_ids is not None:
        conditions.append("site_id IN {allowed_site_ids:Array(String)}")
        params["allowed_site_ids"] = allowed_site_ids
    if flt.protocol is not None:
        conditions.append("protocol = {protocol:UInt8}")
        params["protocol"] = flt.protocol
    if flt.application:
        conditions.append("application = {application:String}")
        params["application"] = flt.application
    if flt.host:
        conditions.append("(src_addr = {host:String} OR dst_addr = {host:String})")
        params["host"] = flt.host

    params["limit"] = PAGE_SIZE
    params["offset"] = (page - 1) * PAGE_SIZE

    query = (
        "SELECT timestamp, site_id, src_addr, dst_addr, src_port, dst_port, protocol, "
        "application, bytes, packets, direction FROM flow_record WHERE "
        + " AND ".join(conditions)
        + " ORDER BY timestamp DESC LIMIT {limit:UInt32} OFFSET {offset:UInt32}"
    )

    client = await clickhouse.get_client()
    rows = await client.query(query, parameters=params)
    return [dict(zip(_COLUMNS, row, strict=True)) for row in rows.result_rows]


async def is_outside_retention(flt: FlowFilter) -> bool:
    """FR-005 edge case: a query entirely older than the retention window must be
    told the data is no longer retained, not shown an empty result indistinguishable
    from "no traffic occurred"."""
    retention_days = await retention_client.get_retention_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    end = flt.end if flt.end.tzinfo else flt.end.replace(tzinfo=timezone.utc)
    return end < cutoff
