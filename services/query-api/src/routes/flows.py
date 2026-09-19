"""GET /flows — drill-down into individual flow records for a filtered window
(User Story 1 & 2, FR-003, FR-006). The "outside_retention" reason (FR-005 edge case)
is added on top of this in User Story 2 (tasks.md T063)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from shared.api.envelope import EmptyReason, Envelope

from .. import clickhouse
from ..auth import require_authenticated

router = APIRouter(tags=["query"])

_PAGE_SIZE = 100


@router.get("/flows")
async def get_flows(
    start: datetime = Query(...),
    end: datetime = Query(...),
    site_id: str | None = Query(None),
    protocol: int | None = Query(None),
    application: str | None = Query(None),
    host: str | None = Query(None),
    page: int = Query(1, ge=1),
    _auth: str = Depends(require_authenticated),
) -> Envelope[list[dict]]:
    conditions = ["timestamp >= {start:DateTime64}", "timestamp <= {end:DateTime64}"]
    params: dict[str, object] = {"start": start, "end": end}

    if site_id:
        conditions.append("site_id = {site_id:String}")
        params["site_id"] = site_id
    if protocol is not None:
        conditions.append("protocol = {protocol:UInt8}")
        params["protocol"] = protocol
    if application:
        conditions.append("application = {application:String}")
        params["application"] = application
    if host:
        conditions.append("(src_addr = {host:String} OR dst_addr = {host:String})")
        params["host"] = host

    offset = (page - 1) * _PAGE_SIZE
    params["limit"] = _PAGE_SIZE
    params["offset"] = offset

    query = (
        "SELECT timestamp, site_id, src_addr, dst_addr, src_port, dst_port, protocol, "
        "application, bytes, packets, direction FROM flow_record WHERE "
        + " AND ".join(conditions)
        + " ORDER BY timestamp DESC LIMIT {limit:UInt32} OFFSET {offset:UInt32}"
    )

    client = await clickhouse.get_client()
    rows = await client.query(query, parameters=params)
    columns = [
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
    data = [dict(zip(columns, row, strict=True)) for row in rows.result_rows]

    empty = len(data) == 0
    return Envelope.of(data, empty=empty, reason=EmptyReason.NO_TRAFFIC if empty else None)
