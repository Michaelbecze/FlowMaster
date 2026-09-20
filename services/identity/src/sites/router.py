"""Minimal Site create/list — unblocks Ingestion attribution (FR-001) and User Story 1's
independent test before the full admin onboarding flow (User Story 3) lands.
GET/POST/PATCH/DELETE /sites."""

from __future__ import annotations

from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit.logger import write_audit_log
from ..auth.session import AuthenticatedUser, require_user
from .. import db

router = APIRouter(prefix="/sites", tags=["sites"])


class SiteCreateRequest(BaseModel):
    name: str
    network_identity: str


class SiteUpdateRequest(BaseModel):
    name: str = Field(min_length=1)


class SiteResponse(BaseModel):
    id: str
    name: str
    network_identity: str
    status: str
    last_seen_at: datetime | None
    created_at: datetime


async def _organization_id(conn) -> str:
    # v1 is single-organization (FR-021); the one row is seeded at deploy time.
    row = await conn.fetchrow("SELECT id FROM organization LIMIT 1")
    return row["id"]


def _to_site_response(row) -> SiteResponse:
    # asyncpg returns UUID columns as uuid.UUID, not str; every field crossing the
    # Pydantic/JSON boundary must be cast explicitly (Pydantic 2 does not coerce UUID -> str).
    data = dict(row)
    data["id"] = str(data["id"])
    return SiteResponse(**data)


@router.get("", response_model=list[SiteResponse])
async def list_sites(user: AuthenticatedUser = Depends(require_user)) -> list[SiteResponse]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, network_identity, status, last_seen_at, created_at FROM site"
        )
    return [_to_site_response(r) for r in rows]


@router.post("", response_model=SiteResponse, status_code=201)
async def create_site(
    body: SiteCreateRequest, user: AuthenticatedUser = Depends(require_user)
) -> SiteResponse:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        org_id = await _organization_id(conn)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO site (organization_id, name, network_identity, created_by)
                VALUES ($1, $2, $3, $4)
                RETURNING id, name, network_identity, status, last_seen_at, created_at
                """,
                org_id,
                body.name,
                body.network_identity,
                user.user_id,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"a site with network_identity '{body.network_identity}' already exists",
            ) from exc
        await write_audit_log(
            conn,
            actor_user_id=user.user_id,
            action="site.created",
            target=str(row["id"]),
            detail={"name": body.name, "network_identity": body.network_identity},
        )
    return _to_site_response(row)


@router.patch("/{site_id}", response_model=SiteResponse)
async def rename_site(
    site_id: str, body: SiteUpdateRequest, user: AuthenticatedUser = Depends(require_user)
) -> SiteResponse:
    """Renames a site (the exporter identity/network_identity is not editable here —
    that's what Ingestion attributes flows by, so changing it is a re-onboard, not a
    rename)."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE site SET name = $2 WHERE id = $1
            RETURNING id, name, network_identity, status, last_seen_at, created_at
            """,
            site_id,
            body.name,
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
        await write_audit_log(
            conn,
            actor_user_id=user.user_id,
            action="site.renamed",
            target=site_id,
            detail={"name": body.name},
        )
    return _to_site_response(row)


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(site_id: str, user: AuthenticatedUser = Depends(require_user)) -> None:
    """Removes the Site row (cascading its UserRoleAssignment scopes via the FK).
    Historical flow data already written to ClickHouse under this site_id is left
    intact — deleting a site is an onboarding/scope action, not a retroactive data
    purge (Edge Cases: referenced-entity cleanup means the *reference* is cleaned up,
    not the analytics history it pointed at)."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM site WHERE id = $1", site_id)
        if result == "DELETE 0":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
        await write_audit_log(
            conn, actor_user_id=user.user_id, action="site.deleted", target=site_id
        )


class SiteSeenRequest(BaseModel):
    seen_at: datetime


# Internal router: called service-to-service over the private Docker network (not
# exposed through the Gateway's public routing table), so Ingestion and Realtime can
# resolve/update Site rows without reaching into identity's PostgreSQL database directly
# (constitution Principle I forbids cross-service data-store access; an HTTP boundary,
# even an internal one, is what keeps identity as Site's sole owner).
internal_router = APIRouter(prefix="/internal/sites", tags=["sites-internal"])


@internal_router.get("/by-network-identity/{network_identity}")
async def resolve_site_by_network_identity(network_identity: str) -> dict[str, str | None]:
    """Used by Ingestion's attribution step (services/ingestion/src/attribution.py)."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM site WHERE network_identity = $1", network_identity
        )
    return {"site_id": str(row["id"]) if row else None}


@internal_router.post("/{site_id}/seen", status_code=204)
async def mark_site_seen(site_id: str, body: SiteSeenRequest) -> None:
    """Used by the Realtime staleness tracker (services/realtime/src/staleness.py)."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE site SET status = 'active', last_seen_at = $2 WHERE id = $1",
            site_id,
            body.seen_at,
        )


class SiteStatusRequest(BaseModel):
    status: str


@internal_router.post("/{site_id}/status", status_code=204)
async def set_site_status(site_id: str, body: SiteStatusRequest) -> None:
    """Used by the Realtime staleness tracker to flip a silent site to 'stale'
    (FR-004) without Realtime writing to identity's database directly."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE site SET status = $2 WHERE id = $1", site_id, body.status)


@internal_router.get("/scope/{user_id}")
async def get_user_site_scope(user_id: str) -> dict:
    """Used by Alerting's evaluator (services/alerting/src/evaluator.py) to
    periodically re-verify a rule owner's *current* site scope — a background job has
    no bearer token to call GET /auth/whoami with, and re-checking at evaluation time
    (not just rule-creation time) is what stops a rule from evaluating a site the
    owner's access to was since revoked (contracts/alerting-api.md)."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT site_id FROM user_role_assignment WHERE user_id = $1", user_id
        )
    if any(r["site_id"] is None for r in rows):
        return {"all_sites": True, "site_ids": []}
    return {"all_sites": False, "site_ids": [str(r["site_id"]) for r in rows]}


@internal_router.get("")
async def list_sites_internal() -> list[dict]:
    """Used by Realtime's staleness sweep to enumerate known sites without a session
    token (service-to-service call on the private network)."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, status, last_seen_at FROM site")
    return [
        {
            "id": str(r["id"]),
            "status": r["status"],
            "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
        }
        for r in rows
    ]
