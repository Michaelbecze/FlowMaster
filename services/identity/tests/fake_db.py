"""A minimal in-memory stand-in for identity's PostgreSQL schema, used by the contract
tests so they run without Testcontainers. It recognizes the exact queries identity's
routers issue (both sides are controlled by this codebase) rather than parsing SQL
generally — a real Postgres exercises the actual schema/constraints in a
Testcontainers-backed CI job per the constitution's Testing Standards.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import asyncpg


def _new_id() -> str:
    return str(uuid.uuid4())


class FakeDatabase:
    def __init__(self) -> None:
        self.organizations: dict[str, dict] = {}
        self.retention_policies: dict[str, dict] = {}
        self.sites: dict[str, dict] = {}
        self.users: dict[str, dict] = {}
        self.roles: dict[str, dict] = {}
        self.role_by_name: dict[str, str] = {}
        self.assignments: list[dict] = []
        self.sessions: dict[str, dict] = {}
        self.api_tokens: dict[str, dict] = {}
        self.audit_log: list[dict] = []

        org_id = _new_id()
        self.organizations[org_id] = {"id": org_id, "name": "Test Org", "retention_policy_id": None}
        rp_id = _new_id()
        self.retention_policies[rp_id] = {
            "id": rp_id,
            "organization_id": org_id,
            "duration_days": 1,
            "updated_at": datetime.now(timezone.utc),
            "updated_by": None,
        }
        self.organizations[org_id]["retention_policy_id"] = rp_id

        for name, permissions in [
            ("viewer", ["dashboard:read", "reports:read"]),
            ("analyst", ["dashboard:read", "reports:read", "reports:write"]),
            ("administrator", ["*"]),
        ]:
            role_id = _new_id()
            self.roles[role_id] = {"id": role_id, "name": name, "permissions": permissions}
            self.role_by_name[name] = role_id

    def add_active_user(self, email: str, password_hash: str) -> str:
        user_id = _new_id()
        org_id = next(iter(self.organizations))
        self.users[user_id] = {
            "id": user_id,
            "organization_id": org_id,
            "email": email,
            "password_hash": password_hash,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        }
        return user_id

    def add_session(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        self.sessions[token_hash] = {
            "token_hash": token_hash,
            "user_id": user_id,
            "expires_at": expires_at,
            "revoked_at": None,
        }


class FakeConnection:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query: str, *args):
        q = " ".join(query.split())

        if "SELECT id FROM organization LIMIT 1" in q:
            org_id = next(iter(self.db.organizations))
            return {"id": org_id}

        if q.startswith("SELECT id, password_hash, status FROM app_user WHERE email"):
            for u in self.db.users.values():
                if u["email"] == args[0]:
                    return dict(u)
            return None

        if "FROM session s" in q and "JOIN app_user u" in q:
            row = self.db.sessions.get(args[0])
            if not row or row["revoked_at"] is not None or row["expires_at"] <= datetime.now(timezone.utc):
                return None
            user = self.db.users.get(row["user_id"])
            return {"user_id": user["id"], "email": user["email"], "status": user["status"]} if user else None

        if "FROM api_token t" in q and "JOIN app_user u" in q:
            row = self.db.api_tokens.get(args[0])
            if not row or row["revoked_at"] is not None:
                return None
            user = self.db.users.get(row["user_id"])
            return {"user_id": user["id"], "email": user["email"], "status": user["status"]} if user else None

        if q.startswith("INSERT INTO api_token"):
            token_hash, user_id = args
            token_id = _new_id()
            self.db.api_tokens[token_hash] = {
                "id": token_id, "token_hash": token_hash, "user_id": user_id,
                "created_at": datetime.now(timezone.utc), "revoked_at": None,
            }
            return {"id": token_id, "created_at": self.db.api_tokens[token_hash]["created_at"]}

        if q.startswith("INSERT INTO site"):
            org_id, name, network_identity, created_by = args
            for s in self.db.sites.values():
                if s["network_identity"] == network_identity:
                    raise asyncpg.exceptions.UniqueViolationError("duplicate key")
            site_id = _new_id()
            row = {
                "id": site_id, "organization_id": org_id, "name": name,
                "network_identity": network_identity, "status": "never_connected",
                "last_seen_at": None, "created_at": datetime.now(timezone.utc), "created_by": created_by,
            }
            self.db.sites[site_id] = row
            return dict(row)

        if q.startswith("SELECT id, name, network_identity, status, last_seen_at, created_at FROM site WHERE"):
            return None

        if q.startswith("UPDATE site SET name"):
            site_id, name = args
            s = self.db.sites.get(site_id)
            if not s:
                return None
            s["name"] = name
            return dict(s)

        if q.startswith("INSERT INTO app_user"):
            org_id, email, password_hash = args
            for u in self.db.users.values():
                if u["email"] == email:
                    raise asyncpg.exceptions.UniqueViolationError("duplicate key")
            user_id = self.db.add_active_user(email, password_hash)
            return dict(self.db.users[user_id])

        if q.startswith("SELECT id FROM role WHERE name"):
            role_id = self.db.role_by_name.get(args[0])
            return {"id": role_id} if role_id else None

        if q.startswith("SELECT id, email, status, created_at FROM app_user WHERE id"):
            u = self.db.users.get(args[0])
            return dict(u) if u else None

        if q.startswith("UPDATE app_user SET status"):
            user_id, new_status = args
            u = self.db.users.get(user_id)
            if not u:
                return None
            u["status"] = new_status
            return dict(u)

        if q.startswith("UPDATE retention_policy"):
            duration_days, updated_by = args
            if not self.db.retention_policies:
                return None
            rp = next(iter(self.db.retention_policies.values()))
            rp["duration_days"] = duration_days
            rp["updated_by"] = updated_by
            rp["updated_at"] = datetime.now(timezone.utc)
            return dict(rp)

        if q.startswith("SELECT id, duration_days, updated_at FROM retention_policy"):
            if not self.db.retention_policies:
                return None
            return dict(next(iter(self.db.retention_policies.values())))

        raise AssertionError(f"FakeConnection.fetchrow: unrecognized query: {q}")

    async def fetch(self, query: str, *args):
        q = " ".join(query.split())

        if q.startswith("SELECT id, email, status, created_at FROM app_user"):
            return [dict(u) for u in self.db.users.values()]

        if "FROM user_role_assignment ura" in q and "JOIN role r" in q:
            return [
                {"role": self.db.roles[a["role_id"]]["name"], "site_id": a["site_id"]}
                for a in self.db.assignments
                if a["user_id"] == args[0]
            ]

        if q.startswith("SELECT site_id FROM user_role_assignment WHERE user_id"):
            return [{"site_id": a["site_id"]} for a in self.db.assignments if a["user_id"] == args[0]]

        if q.startswith("SELECT id, name, network_identity, status, last_seen_at, created_at FROM site"):
            return [dict(s) for s in self.db.sites.values()]

        if q.startswith("SELECT id, status, last_seen_at FROM site"):
            return [{"id": s["id"], "status": s["status"], "last_seen_at": s["last_seen_at"]} for s in self.db.sites.values()]

        if q.startswith("SELECT id, actor_user_id, action, target, occurred_at, detail FROM audit_log_entry WHERE action"):
            return [e for e in self.db.audit_log if e["action"] == args[0]][: args[1]]

        if q.startswith("SELECT id, actor_user_id, action, target, occurred_at, detail FROM audit_log_entry"):
            return list(reversed(self.db.audit_log))[: args[0]]

        raise AssertionError(f"FakeConnection.fetch: unrecognized query: {q}")

    async def execute(self, query: str, *args):
        q = " ".join(query.split())

        if q.startswith("INSERT INTO session"):
            token_hash, user_id, expires_at = args
            self.db.sessions[token_hash] = {
                "token_hash": token_hash, "user_id": user_id, "expires_at": expires_at, "revoked_at": None,
            }
            return "INSERT 0 1"

        if q.startswith("UPDATE session SET revoked_at"):
            row = self.db.sessions.get(args[0])
            if row:
                row["revoked_at"] = datetime.now(timezone.utc)
            return "UPDATE 1" if row else "UPDATE 0"

        if q.startswith("UPDATE api_token SET revoked_at"):
            for row in self.db.api_tokens.values():
                if row["id"] == args[0] and row["user_id"] == args[1] and row["revoked_at"] is None:
                    row["revoked_at"] = datetime.now(timezone.utc)
                    return "UPDATE 1"
            return "UPDATE 0"

        if q.startswith("UPDATE site SET status = 'active'"):
            site_id, seen_at = args
            s = self.db.sites.get(site_id)
            if s:
                s["status"] = "active"
                s["last_seen_at"] = seen_at
            return "UPDATE 1" if s else "UPDATE 0"

        if q.startswith("UPDATE site SET status"):
            site_id, new_status = args
            s = self.db.sites.get(site_id)
            if s:
                s["status"] = new_status
            return "UPDATE 1" if s else "UPDATE 0"

        if q.startswith("DELETE FROM site WHERE id"):
            existed = args[0] in self.db.sites
            self.db.sites.pop(args[0], None)
            self.db.assignments = [a for a in self.db.assignments if a.get("site_id") != args[0]]
            return "DELETE 1" if existed else "DELETE 0"

        if q.startswith("DELETE FROM app_user WHERE id"):
            user_id = args[0]
            if user_id not in self.db.users:
                return "DELETE 0"
            referenced = (
                any(s["created_by"] == user_id for s in self.db.sites.values())
                or any(rp["updated_by"] == user_id for rp in self.db.retention_policies.values())
                or any(e["actor_user_id"] == user_id for e in self.db.audit_log)
            )
            if referenced:
                raise asyncpg.exceptions.ForeignKeyViolationError("update or delete violates foreign key constraint")
            self.db.users.pop(user_id, None)
            self.db.assignments = [a for a in self.db.assignments if a["user_id"] != user_id]
            self.db.sessions = {k: v for k, v in self.db.sessions.items() if v["user_id"] != user_id}
            self.db.api_tokens = {k: v for k, v in self.db.api_tokens.items() if v["user_id"] != user_id}
            return "DELETE 1"

        if q.startswith("DELETE FROM user_role_assignment WHERE user_id"):
            before = len(self.db.assignments)
            self.db.assignments = [a for a in self.db.assignments if a["user_id"] != args[0]]
            return f"DELETE {before - len(self.db.assignments)}"

        if q.startswith("INSERT INTO user_role_assignment"):
            # invite_user hardcodes "VALUES ($1, $2, NULL)" (org-wide scope on invite,
            # 2 bound args); update_user_roles binds all three placeholders.
            if q.endswith("VALUES ($1, $2, NULL)"):
                user_id, role_id = args
                site_id = None
            else:
                user_id, role_id, site_id = args
            self.db.assignments.append({"user_id": user_id, "role_id": role_id, "site_id": site_id})
            return "INSERT 0 1"

        if q.startswith("INSERT INTO audit_log_entry"):
            actor_user_id, action, target, detail = args
            self.db.audit_log.append(
                {
                    "id": _new_id(),
                    "actor_user_id": actor_user_id,
                    "action": action,
                    "target": target,
                    "occurred_at": datetime.now(timezone.utc),
                    "detail": detail,
                }
            )
            return "INSERT 0 1"

        raise AssertionError(f"FakeConnection.execute: unrecognized query: {q}")


class FakePool:
    def __init__(self, db: FakeDatabase | None = None) -> None:
        self.db = db or FakeDatabase()

    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection(self.db)
