"""Audit-log writing, shared by every mutating Identity endpoint (FR-011).

Every mutating call on this service MUST write an entry — a contractual requirement
of the endpoint itself per contracts/identity-api.md, not an optional side effect.
"""

from __future__ import annotations

import json

import asyncpg


async def write_audit_log(
    conn: asyncpg.Connection,
    *,
    actor_user_id: str,
    action: str,
    target: str,
    detail: dict | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO audit_log_entry (actor_user_id, action, target, detail)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        actor_user_id,
        action,
        target,
        json.dumps(detail or {}),
    )
