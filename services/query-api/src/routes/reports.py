"""POST /reports, GET /reports/{id}, GET /reports/{id}/export — User Story 2, FR-006/FR-007.

A Report row stores only the filter_definition; "current results" (and the export) are
always computed live against ClickHouse via the same query GET /flows uses, so an export
matches exactly what a report view would show on screen (SC-009).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from starlette.responses import PlainTextResponse

from shared.api.envelope import EmptyReason, Envelope

from .. import db
from ..auth import require_authenticated
from ..flow_query import FlowFilter, is_outside_retention, query_flows

router = APIRouter(tags=["query"])


class ReportCreateRequest(BaseModel):
    start: datetime
    end: datetime
    site_id: str | None = None
    protocol: int | None = None
    application: str | None = None
    host: str | None = None
    name: str | None = None


class ReportResponse(BaseModel):
    id: str
    name: str | None
    filter_definition: dict
    created_at: datetime


def _to_report_response(row) -> ReportResponse:
    return ReportResponse(
        id=str(row["id"]),
        name=row["name"],
        filter_definition=json.loads(row["filter_definition"]),
        created_at=row["created_at"],
    )


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreateRequest, auth: str = Depends(require_authenticated)
) -> ReportResponse:
    flt = FlowFilter(
        start=body.start,
        end=body.end,
        site_id=body.site_id,
        protocol=body.protocol,
        application=body.application,
        host=body.host,
    )
    # v1 has no per-user identity threading into query-api yet (US3's shared authz
    # dependency, tasks.md T078); reports are owned by a placeholder until then.
    owner_user_id = "00000000-0000-0000-0000-000000000000"

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO report (owner_user_id, filter_definition, name)
            VALUES ($1::uuid, $2::jsonb, $3)
            RETURNING id, name, filter_definition, created_at
            """,
            owner_user_id,
            json.dumps(flt.to_dict()),
            body.name,
        )
    return _to_report_response(row)


async def _load_filter(report_id: str) -> FlowFilter:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT filter_definition FROM report WHERE id = $1::uuid", report_id
        )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")

    return FlowFilter.from_dict(json.loads(row["filter_definition"]))


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str, auth: str = Depends(require_authenticated)
) -> Envelope[list[dict]]:
    flt = await _load_filter(report_id)
    data = await query_flows(flt)

    if not data:
        reason = (
            EmptyReason.OUTSIDE_RETENTION
            if await is_outside_retention(flt)
            else EmptyReason.NO_TRAFFIC
        )
        return Envelope.of(data, empty=True, reason=reason)
    return Envelope.of(data, empty=False)


@router.get("/reports/{report_id}/export")
async def export_report(
    report_id: str,
    format: str = Query("csv"),
    auth: str = Depends(require_authenticated),
) -> PlainTextResponse:
    if format != "csv":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "only format=csv is supported")

    flt = await _load_filter(report_id)
    data = await query_flows(flt)

    buffer = io.StringIO()
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
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in data:
        writer.writerow(row)

    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.csv"'},
    )
