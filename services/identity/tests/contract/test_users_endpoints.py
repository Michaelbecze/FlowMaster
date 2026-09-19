"""Contract tests for GET/POST /users, PATCH /users/{id}/roles, PATCH /users/{id}/status
(User Story 3, FR-008/FR-009), against the in-memory fake_db.FakePool."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.db as db_module
from src.auth.session import hash_password
from src.main import app
from tests.fake_db import FakeDatabase, FakePool


@pytest.fixture
def db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture(autouse=True)
def patch_pool(monkeypatch, db: FakeDatabase):
    pool = FakePool(db)

    async def _get_pool():
        return pool

    monkeypatch.setattr(db_module, "get_pool", _get_pool)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login_as_admin(client: TestClient, db: FakeDatabase) -> dict[str, str]:
    user_id = db.add_active_user("admin@example.com", hash_password("changeme"))
    resp = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "changeme"}
    )
    assert resp.status_code == 200
    token = resp.json()["session_token"]
    return {"Authorization": f"Bearer {token}"}, user_id


class TestListAndInviteUsers:
    def test_invited_user_appears_in_list_with_its_role(self, client, db) -> None:
        headers, _ = _login_as_admin(client, db)

        invite_resp = client.post(
            "/users",
            json={"email": "analyst@example.com", "password": "changeme123", "role": "analyst"},
            headers=headers,
        )
        assert invite_resp.status_code == 201
        assert invite_resp.json()["roles"] == [{"role": "analyst", "site_id": None}]

        list_resp = client.get("/users", headers=headers)
        emails = [u["email"] for u in list_resp.json()]
        assert "analyst@example.com" in emails

    def test_duplicate_email_is_rejected(self, client, db) -> None:
        headers, _ = _login_as_admin(client, db)
        client.post(
            "/users",
            json={"email": "dup@example.com", "password": "changeme123"},
            headers=headers,
        )

        resp = client.post(
            "/users",
            json={"email": "dup@example.com", "password": "changeme123"},
            headers=headers,
        )

        assert resp.status_code == 409

    def test_unknown_role_is_rejected(self, client, db) -> None:
        headers, _ = _login_as_admin(client, db)

        resp = client.post(
            "/users",
            json={"email": "x@example.com", "password": "changeme123", "role": "superuser"},
            headers=headers,
        )

        assert resp.status_code == 422

    def test_invite_writes_an_audit_log_entry(self, client, db) -> None:
        headers, _ = _login_as_admin(client, db)

        client.post(
            "/users",
            json={"email": "audited@example.com", "password": "changeme123"},
            headers=headers,
        )

        assert any(e["action"] == "user.invited" for e in db.audit_log)


class TestUpdateUserRoles:
    def test_roles_are_replaced_not_merged(self, client, db) -> None:
        headers, _ = _login_as_admin(client, db)
        invite_resp = client.post(
            "/users",
            json={"email": "scoped@example.com", "password": "changeme123", "role": "viewer"},
            headers=headers,
        )
        user_id = invite_resp.json()["id"]

        resp = client.patch(
            f"/users/{user_id}/roles",
            json={"roles": [{"role": "analyst", "site_id": "site-1"}]},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["roles"] == [{"role": "analyst", "site_id": "site-1"}]

    def test_unknown_user_is_404(self, client, db) -> None:
        headers, _ = _login_as_admin(client, db)

        resp = client.patch(
            "/users/does-not-exist/roles", json={"roles": []}, headers=headers
        )

        assert resp.status_code == 404


class TestUpdateUserStatus:
    def test_disabling_a_user_denies_their_next_request(self, client, db) -> None:
        admin_headers, _ = _login_as_admin(client, db)
        invited = client.post(
            "/users",
            json={"email": "tobedisabled@example.com", "password": "changeme123"},
            headers=admin_headers,
        ).json()

        login_resp = client.post(
            "/auth/login",
            json={"email": "tobedisabled@example.com", "password": "changeme123"},
        )
        target_headers = {"Authorization": f"Bearer {login_resp.json()['session_token']}"}

        disable_resp = client.patch(
            f"/users/{invited['id']}/status", json={"status": "disabled"}, headers=admin_headers
        )
        assert disable_resp.status_code == 200

        # User Story 3, Acceptance Scenario 3: denied on the very next request.
        whoami_resp = client.get("/auth/whoami", headers=target_headers)
        assert whoami_resp.status_code == 401

    def test_invalid_status_value_is_rejected(self, client, db) -> None:
        headers, user_id = _login_as_admin(client, db)

        resp = client.patch(
            f"/users/{user_id}/status", json={"status": "on-vacation"}, headers=headers
        )

        assert resp.status_code == 422
