"""Internal, service-to-service read of the organization's retention window.

Used by query-api to flag a historical query as "outside_retention" rather than an
indistinguishable empty result (FR-005 edge case, tasks.md T063). The authenticated,
admin-facing GET/PATCH /retention-policy endpoint is User Story 3's scope (T077); this
is deliberately separate (internal, read-only, unauthenticated on the private network)
so US2's retention-awareness doesn't have to wait on US3's admin UI.
"""

from __future__ import annotations

from fastapi import APIRouter

from .. import db

internal_router = APIRouter(prefix="/internal/retention-policy", tags=["retention-internal"])


@internal_router.get("")
async def get_retention_policy_internal() -> dict[str, int]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT duration_days FROM retention_policy LIMIT 1")
    return {"duration_days": row["duration_days"] if row else 1}
