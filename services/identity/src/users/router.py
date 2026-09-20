"""GET/POST /users, PATCH /users/{id}/roles, PATCH /users/{id}/status, DELETE /users/{id}
— User Story 3, FR-008/FR-009. Every mutation writes an AuditLogEntry (FR-011)."""

from __future__ import annotations

from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..audit.logger import write_audit_log
from ..auth.session import AuthenticatedUser, hash_password, require_user
from .. import db

router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    id: str
    email: str
    status: str
    created_at: datetime


class RoleAssignment(BaseModel):
    role: str
    site_id: str | None = None


class UserWithRolesResponse(UserResponse):
    roles: list[RoleAssignment]


def _to_user_response(row) -> UserResponse:
    return UserResponse(
        id=str(row["id"]), email=row["email"], status=row["status"], created_at=row["created_at"]
    )


async def _organization_id(conn) -> str:
    row = await conn.fetchrow("SELECT id FROM organization LIMIT 1")
    return row["id"]


async def _load_roles(conn, user_id: str) -> list[RoleAssignment]:
    rows = await conn.fetch(
        """
        SELECT r.name AS role, ura.site_id
        FROM user_role_assignment ura
        JOIN role r ON r.id = ura.role_id
        WHERE ura.user_id = $1
        """,
        user_id,
    )
    return [RoleAssignment(role=r["role"], site_id=str(r["site_id"]) if r["site_id"] else None) for r in rows]


@router.get("", response_model=list[UserWithRolesResponse])
async def list_users(
    user: AuthenticatedUser = Depends(require_user),
) -> list[UserWithRolesResponse]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, email, status, created_at FROM app_user")
        result = []
        for r in rows:
            roles = await _load_roles(conn, r["id"])
            result.append(UserWithRolesResponse(**_to_user_response(r).model_dump(), roles=roles))
    return result


class UserInviteRequest(BaseModel):
    email: str
    password: str
    role: str = "viewer"


@router.post("", response_model=UserWithRolesResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: UserInviteRequest, actor: AuthenticatedUser = Depends(require_user)
) -> UserWithRolesResponse:
    """v1 has no outbound email/SSO (FR-020 Assumptions), so onboarding is
    administrator-set-password rather than an email invite link."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        org_id = await _organization_id(conn)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO app_user (organization_id, email, password_hash)
                VALUES ($1, $2, $3)
                RETURNING id, email, status, created_at
                """,
                org_id,
                body.email,
                hash_password(body.password),
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"a user with email '{body.email}' already exists"
            ) from exc

        role_row = await conn.fetchrow("SELECT id FROM role WHERE name = $1", body.role)
        if role_row is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown role '{body.role}'")
        await conn.execute(
            "INSERT INTO user_role_assignment (user_id, role_id, site_id) VALUES ($1, $2, NULL)",
            row["id"],
            role_row["id"],
        )
        await write_audit_log(
            conn,
            actor_user_id=actor.user_id,
            action="user.invited",
            target=str(row["id"]),
            detail={"email": body.email, "role": body.role},
        )

    return UserWithRolesResponse(
        **_to_user_response(row).model_dump(),
        roles=[RoleAssignment(role=body.role, site_id=None)],
    )


class RolesUpdateRequest(BaseModel):
    roles: list[RoleAssignment]


@router.patch("/{user_id}/roles", response_model=UserWithRolesResponse)
async def update_user_roles(
    user_id: str, body: RolesUpdateRequest, actor: AuthenticatedUser = Depends(require_user)
) -> UserWithRolesResponse:
    """Replaces the user's role/site-scope assignments (FR-008); every other service
    treats identity's assignments as the single point of truth for FR-009."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT id, email, status, created_at FROM app_user WHERE id = $1", user_id
        )
        if user_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

        async with conn.transaction():
            await conn.execute("DELETE FROM user_role_assignment WHERE user_id = $1", user_id)
            for assignment in body.roles:
                role_row = await conn.fetchrow("SELECT id FROM role WHERE name = $1", assignment.role)
                if role_row is None:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown role '{assignment.role}'"
                    )
                await conn.execute(
                    "INSERT INTO user_role_assignment (user_id, role_id, site_id) VALUES ($1, $2, $3)",
                    user_id,
                    role_row["id"],
                    assignment.site_id,
                )
            await write_audit_log(
                conn,
                actor_user_id=actor.user_id,
                action="user.role_changed",
                target=user_id,
                detail={"roles": [a.model_dump() for a in body.roles]},
            )

        roles = await _load_roles(conn, user_id)
    return UserWithRolesResponse(**_to_user_response(user_row).model_dump(), roles=roles)


class StatusUpdateRequest(BaseModel):
    status: str


@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: str, body: StatusUpdateRequest, actor: AuthenticatedUser = Depends(require_user)
) -> UserResponse:
    """Disabling a user revokes access on their very next request, not eventually:
    every session/API-token check (auth/session.py get_current_user) re-verifies
    app_user.status on each call, so there is nothing to restart (User Story 3,
    Acceptance Scenario 3)."""
    if body.status not in ("active", "disabled"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "status must be active or disabled")

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE app_user SET status = $2 WHERE id = $1 "
            "RETURNING id, email, status, created_at",
            user_id,
            body.status,
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

        await write_audit_log(
            conn,
            actor_user_id=actor.user_id,
            action="user.status_changed",
            target=user_id,
            detail={"status": body.status},
        )
    return _to_user_response(row)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, actor: AuthenticatedUser = Depends(require_user)) -> None:
    """Permanently removes the user (sessions/API tokens/role assignments cascade via
    their FKs). Unlike PATCH .../status, this cannot be undone — use disable for
    ordinary access revocation.

    A user who has ever performed an audited action, onboarded a site, or updated the
    retention policy cannot be hard-deleted: those tables reference app_user without
    ON DELETE CASCADE, by design, so deleting the account can never silently erase
    audit history (FR-011). Disable such accounts instead."""
    if user_id == actor.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute("DELETE FROM app_user WHERE id = $1", user_id)
        except asyncpg.ForeignKeyViolationError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This user has audit history, a site, or a retention policy change "
                "attributed to them and cannot be permanently deleted — disable the "
                "account instead to revoke access while preserving that history.",
            ) from exc
        if result == "DELETE 0":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

        await write_audit_log(
            conn, actor_user_id=actor.user_id, action="user.deleted", target=user_id
        )
