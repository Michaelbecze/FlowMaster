"""Password hashing and session-token issuance/validation.

POST /auth/login, POST /auth/logout. Session tokens are short-lived and revocable so that
role/access changes take effect on the user's very next request without a restart
(contracts/identity-api.md Access-control contract).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..config import get_settings
from ..db import get_pool

router = APIRouter(prefix="/auth", tags=["auth"])


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _hash_token(token: str) -> str:
    # Only the hash is stored, so a leaked database backup does not leak usable tokens.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    session_token: str
    expires_at: datetime


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash, status FROM app_user WHERE email = $1", body.email
        )
        if row is None or row["status"] != "active" or row["password_hash"] is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        if not verify_password(body.password, row["password_hash"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

        token = secrets.token_urlsafe(32)
        settings = get_settings()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)
        await conn.execute(
            "INSERT INTO session (token_hash, user_id, expires_at) VALUES ($1, $2, $3)",
            _hash_token(token),
            row["id"],
            expires_at,
        )
        return LoginResponse(session_token=token, expires_at=expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(authorization: str = Header(...)) -> None:
    token = _bearer_token(authorization)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE session SET revoked_at = now() WHERE token_hash = $1", _hash_token(token)
        )


def _bearer_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


class AuthenticatedUser(BaseModel):
    user_id: str
    email: str


async def get_current_user(authorization: str = Header(...)) -> AuthenticatedUser:
    """Shared dependency: validates a session token (interactive login) or an API token
    (machine-client access, FR-019) on every request, not just at login, so a revoked
    user's very next request is denied (User Story 3, Acceptance Scenario 3)."""
    token = _bearer_token(authorization)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.user_id, u.email, u.status
            FROM session s
            JOIN app_user u ON u.id = s.user_id
            WHERE s.token_hash = $1
              AND s.revoked_at IS NULL
              AND s.expires_at > now()
            """,
            _hash_token(token),
        )
        if row is None:
            row = await conn.fetchrow(
                """
                SELECT t.user_id, u.email, u.status
                FROM api_token t
                JOIN app_user u ON u.id = t.user_id
                WHERE t.token_hash = $1 AND t.revoked_at IS NULL
                """,
                _hash_token(token),
            )
        if row is None or row["status"] != "active":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials")
        return AuthenticatedUser(user_id=str(row["user_id"]), email=row["email"])


async def require_user(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    return user


@router.get("/whoami", response_model=AuthenticatedUser)
async def whoami(user: AuthenticatedUser = Depends(require_user)) -> AuthenticatedUser:
    """Validated by the Gateway's AuthMiddleware on every non-public request
    (gateway/src/middleware/auth.py) — the single point of truth for token validity."""
    return user
