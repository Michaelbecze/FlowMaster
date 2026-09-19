"""API-token issuance/revocation for machine-client access, separate from interactive
session login (FR-019). POST /auth/tokens, DELETE /auth/tokens/{id}."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import get_pool
from .session import AuthenticatedUser, require_user

router = APIRouter(prefix="/auth/tokens", tags=["auth"])


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ApiTokenResponse(BaseModel):
    id: str
    api_token: str
    created_at: datetime


@router.post("", response_model=ApiTokenResponse, status_code=status.HTTP_201_CREATED)
async def issue_token(user: AuthenticatedUser = Depends(require_user)) -> ApiTokenResponse:
    """Scoped to the caller's own permissions — an API token can never grant more access
    than the issuing user already has (contracts/identity-api.md)."""
    token = f"fmat_{secrets.token_urlsafe(32)}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO api_token (token_hash, user_id) VALUES ($1, $2) "
            "RETURNING id, created_at",
            _hash_token(token),
            user.user_id,
        )
    return ApiTokenResponse(id=str(row["id"]), api_token=token, created_at=row["created_at"])


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: str, user: AuthenticatedUser = Depends(require_user)) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE api_token SET revoked_at = now() "
            "WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL",
            token_id,
            user.user_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
