"""GET/POST /rules, PATCH/DELETE /rules/{id} — User Story 4, FR-012.

An alert rule is only evaluatable against sites within the owner's access scope, at
creation time and at evaluation time (contracts/alerting-api.md): creation is checked
here against the caller's Principal; evaluation re-checks against the owner's *current*
scope on every tick (services/alerting/src/evaluator.py), so a later access-scope
reduction stops the rule from evaluating sites no longer in scope, consistent with
FR-009.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from shared.authz import Principal, require_site_scope

from .. import db

router = APIRouter(prefix="/rules", tags=["rules"])

_SUPPORTED_CONDITION_TYPES = {"volume_threshold"}


class ConditionDefinition(BaseModel):
    type: str
    bytes_threshold: int
    window_seconds: int = 300


class RuleCreateRequest(BaseModel):
    site_id: str | None = None
    condition: ConditionDefinition
    notification_target: dict = {}
    enabled: bool = True


class RuleUpdateRequest(BaseModel):
    condition: ConditionDefinition | None = None
    notification_target: dict | None = None
    enabled: bool | None = None


class RuleResponse(BaseModel):
    id: str
    owner_user_id: str
    site_id: str | None
    condition: dict
    notification_target: dict
    enabled: bool
    created_at: datetime


def _to_response(row) -> RuleResponse:
    return RuleResponse(
        id=str(row["id"]),
        owner_user_id=str(row["owner_user_id"]),
        site_id=str(row["site_scope"]) if row["site_scope"] else None,
        condition=json.loads(row["condition_definition"]),
        notification_target=json.loads(row["notification_target"]),
        enabled=row["enabled"],
        created_at=row["created_at"],
    )


@router.get("", response_model=list[RuleResponse])
async def list_rules(principal: Principal = Depends(require_site_scope)) -> list[RuleResponse]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, owner_user_id, site_scope, condition_definition, "
            "notification_target, enabled, created_at FROM alert_rule "
            "WHERE owner_user_id = $1",
            principal.user_id,
        )
    return [_to_response(r) for r in rows]


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreateRequest, principal: Principal = Depends(require_site_scope)
) -> RuleResponse:
    if body.condition.type not in _SUPPORTED_CONDITION_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unsupported condition type '{body.condition.type}'; supported: {sorted(_SUPPORTED_CONDITION_TYPES)}",
        )
    if body.site_id is not None and not principal.is_allowed(body.site_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "site outside your access scope")

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO alert_rule
                (owner_user_id, site_scope, condition_definition, notification_target, enabled)
            VALUES ($1::uuid, $2::uuid, $3::jsonb, $4::jsonb, $5)
            RETURNING id, owner_user_id, site_scope, condition_definition,
                      notification_target, enabled, created_at
            """,
            principal.user_id,
            body.site_id,
            json.dumps(body.condition.model_dump()),
            json.dumps(body.notification_target),
            body.enabled,
        )
    return _to_response(row)


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: str, body: RuleUpdateRequest, principal: Principal = Depends(require_site_scope)
) -> RuleResponse:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT owner_user_id FROM alert_rule WHERE id = $1::uuid", rule_id
        )
        if existing is None or str(existing["owner_user_id"]) != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")

        row = await conn.fetchrow(
            """
            UPDATE alert_rule SET
                condition_definition = COALESCE($2::jsonb, condition_definition),
                notification_target = COALESCE($3::jsonb, notification_target),
                enabled = COALESCE($4, enabled)
            WHERE id = $1::uuid
            RETURNING id, owner_user_id, site_scope, condition_definition,
                      notification_target, enabled, created_at
            """,
            rule_id,
            json.dumps(body.condition.model_dump()) if body.condition else None,
            json.dumps(body.notification_target) if body.notification_target is not None else None,
            body.enabled,
        )
    return _to_response(row)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: str, principal: Principal = Depends(require_site_scope)) -> None:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM alert_rule WHERE id = $1::uuid AND owner_user_id = $2::uuid",
            rule_id,
            principal.user_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
