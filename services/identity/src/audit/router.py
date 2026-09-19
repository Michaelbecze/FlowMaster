"""GET /audit-log — query the audit trail (FR-011)."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth.session import AuthenticatedUser, require_user
from .. import db

router = APIRouter(prefix="/audit-log", tags=["audit"])


class AuditLogEntryResponse(BaseModel):
    id: str
    actor_user_id: str
    action: str
    target: str
    occurred_at: datetime
    detail: dict


@router.get("", response_model=list[AuditLogEntryResponse])
async def list_audit_log(
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user: AuthenticatedUser = Depends(require_user),
) -> list[AuditLogEntryResponse]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        if action:
            rows = await conn.fetch(
                "SELECT id, actor_user_id, action, target, occurred_at, detail "
                "FROM audit_log_entry WHERE action = $1 ORDER BY occurred_at DESC LIMIT $2",
                action,
                limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, actor_user_id, action, target, occurred_at, detail "
                "FROM audit_log_entry ORDER BY occurred_at DESC LIMIT $1",
                limit,
            )

    return [
        AuditLogEntryResponse(
            id=str(r["id"]),
            actor_user_id=str(r["actor_user_id"]),
            action=r["action"],
            target=r["target"],
            occurred_at=r["occurred_at"],
            detail=json.loads(r["detail"]),
        )
        for r in rows
    ]
