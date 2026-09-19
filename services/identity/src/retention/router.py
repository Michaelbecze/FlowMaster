"""GET/PATCH /retention-policy — view/update the organization's configured retention
window (FR-005). The internal, unauthenticated read used by other services for
retention-awareness lives in internal_router.py."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..audit.logger import write_audit_log
from ..auth.session import AuthenticatedUser, require_user
from .. import db

router = APIRouter(prefix="/retention-policy", tags=["retention"])


class RetentionPolicyResponse(BaseModel):
    id: str
    duration_days: int
    updated_at: datetime


class RetentionPolicyUpdateRequest(BaseModel):
    duration_days: int


def _to_response(row) -> RetentionPolicyResponse:
    return RetentionPolicyResponse(
        id=str(row["id"]), duration_days=row["duration_days"], updated_at=row["updated_at"]
    )


@router.get("", response_model=RetentionPolicyResponse)
async def get_retention_policy(
    user: AuthenticatedUser = Depends(require_user),
) -> RetentionPolicyResponse:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, duration_days, updated_at FROM retention_policy LIMIT 1")
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No retention policy configured")
    return _to_response(row)


@router.patch("", response_model=RetentionPolicyResponse)
async def update_retention_policy(
    body: RetentionPolicyUpdateRequest, user: AuthenticatedUser = Depends(require_user)
) -> RetentionPolicyResponse:
    if body.duration_days <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "duration_days must be positive")

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE retention_policy
            SET duration_days = $1, updated_at = now(), updated_by = $2
            WHERE id = (SELECT id FROM retention_policy LIMIT 1)
            RETURNING id, duration_days, updated_at
            """,
            body.duration_days,
            user.user_id,
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No retention policy configured")
        await write_audit_log(
            conn,
            actor_user_id=user.user_id,
            action="retention_policy.updated",
            target=str(row["id"]),
            detail={"duration_days": body.duration_days},
        )
    return _to_response(row)
