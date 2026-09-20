"""Contract tests for GET/POST/PATCH/DELETE /sites, GET /audit-log,
GET/PATCH /retention-policy (User Story 3, FR-005/FR-010/FR-011)."""

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


@pytest.fixture
def auth_headers(client: TestClient, db: FakeDatabase) -> dict[str, str]:
    db.add_active_user("admin@example.com", hash_password("changeme"))
    resp = client.post("/auth/login", json={"email": "admin@example.com", "password": "changeme"})
    return {"Authorization": f"Bearer {resp.json()['session_token']}"}


class TestSitesEndpoints:
    def test_onboarded_site_appears_in_list(self, client, auth_headers) -> None:
        create_resp = client.post(
            "/sites", json={"name": "hq", "network_identity": "203.0.113.10"}, headers=auth_headers
        )
        assert create_resp.status_code == 201

        list_resp = client.get("/sites", headers=auth_headers)
        assert any(s["network_identity"] == "203.0.113.10" for s in list_resp.json())

    def test_duplicate_network_identity_is_rejected(self, client, auth_headers) -> None:
        client.post(
            "/sites", json={"name": "hq", "network_identity": "203.0.113.20"}, headers=auth_headers
        )

        resp = client.post(
            "/sites", json={"name": "hq-2", "network_identity": "203.0.113.20"}, headers=auth_headers
        )

        assert resp.status_code == 409

    def test_deleted_site_no_longer_appears_in_list(self, client, auth_headers) -> None:
        create_resp = client.post(
            "/sites", json={"name": "branch", "network_identity": "203.0.113.30"}, headers=auth_headers
        )
        site_id = create_resp.json()["id"]

        delete_resp = client.delete(f"/sites/{site_id}", headers=auth_headers)
        assert delete_resp.status_code == 204

        list_resp = client.get("/sites", headers=auth_headers)
        assert all(s["id"] != site_id for s in list_resp.json())

    def test_deleting_unknown_site_is_404(self, client, auth_headers) -> None:
        resp = client.delete("/sites/does-not-exist", headers=auth_headers)

        assert resp.status_code == 404

    def test_renaming_a_site_updates_it_and_leaves_network_identity_alone(self, client, auth_headers) -> None:
        create_resp = client.post(
            "/sites", json={"name": "unnamed-branch", "network_identity": "203.0.113.70"}, headers=auth_headers
        )
        site_id = create_resp.json()["id"]

        rename_resp = client.patch(f"/sites/{site_id}", json={"name": "Chicago Branch"}, headers=auth_headers)

        assert rename_resp.status_code == 200
        assert rename_resp.json()["name"] == "Chicago Branch"
        assert rename_resp.json()["network_identity"] == "203.0.113.70"

        list_resp = client.get("/sites", headers=auth_headers)
        assert any(s["id"] == site_id and s["name"] == "Chicago Branch" for s in list_resp.json())

    def test_renaming_unknown_site_is_404(self, client, auth_headers) -> None:
        resp = client.patch("/sites/does-not-exist", json={"name": "x"}, headers=auth_headers)

        assert resp.status_code == 404

    def test_renaming_to_an_empty_name_is_rejected(self, client, auth_headers) -> None:
        create_resp = client.post(
            "/sites", json={"name": "branch-2", "network_identity": "203.0.113.71"}, headers=auth_headers
        )
        site_id = create_resp.json()["id"]

        resp = client.patch(f"/sites/{site_id}", json={"name": ""}, headers=auth_headers)

        assert resp.status_code == 422

    def test_rename_is_audited(self, client, auth_headers, db) -> None:
        create_resp = client.post(
            "/sites", json={"name": "branch-3", "network_identity": "203.0.113.72"}, headers=auth_headers
        )
        site_id = create_resp.json()["id"]

        client.patch(f"/sites/{site_id}", json={"name": "Renamed"}, headers=auth_headers)

        assert any(
            e["action"] == "site.renamed" and e["target"] == site_id for e in db.audit_log
        )

    def test_site_creation_and_deletion_are_audited(self, client, auth_headers, db) -> None:
        create_resp = client.post(
            "/sites", json={"name": "audited", "network_identity": "203.0.113.40"}, headers=auth_headers
        )
        site_id = create_resp.json()["id"]
        client.delete(f"/sites/{site_id}", headers=auth_headers)

        actions = [e["action"] for e in db.audit_log]
        assert "site.created" in actions
        assert "site.deleted" in actions


class TestAuditLogEndpoint:
    def test_lists_entries_newest_first(self, client, auth_headers) -> None:
        client.post(
            "/sites", json={"name": "a", "network_identity": "203.0.113.50"}, headers=auth_headers
        )
        client.post(
            "/sites", json={"name": "b", "network_identity": "203.0.113.51"}, headers=auth_headers
        )

        resp = client.get("/audit-log", headers=auth_headers)

        entries = resp.json()
        assert len(entries) >= 2
        assert entries[0]["occurred_at"] >= entries[1]["occurred_at"]

    def test_filters_by_action(self, client, auth_headers) -> None:
        client.post(
            "/sites", json={"name": "c", "network_identity": "203.0.113.60"}, headers=auth_headers
        )

        resp = client.get("/audit-log?action=site.created", headers=auth_headers)

        assert all(e["action"] == "site.created" for e in resp.json())


class TestRetentionPolicyEndpoints:
    def test_get_returns_the_seeded_policy(self, client, auth_headers) -> None:
        resp = client.get("/retention-policy", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["duration_days"] == 1

    def test_patch_updates_duration_and_is_audited(self, client, auth_headers, db) -> None:
        resp = client.patch("/retention-policy", json={"duration_days": 30}, headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["duration_days"] == 30
        assert any(e["action"] == "retention_policy.updated" for e in db.audit_log)

    def test_non_positive_duration_is_rejected(self, client, auth_headers) -> None:
        resp = client.patch("/retention-policy", json={"duration_days": 0}, headers=auth_headers)

        assert resp.status_code == 422
