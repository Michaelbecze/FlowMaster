"""Contract tests for GET/POST /rules, PATCH/DELETE /rules/{id}, GET /events,
GET /events/{id}/flows (User Story 4, FR-012)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import Header, HTTPException, status
from fastapi.testclient import TestClient
from shared.authz import Principal, require_site_scope

import src.db as db_module
from src.main import app
from tests.fake_db import FakeDatabase, FakePool

AUTH_HEADERS = {"Authorization": "Bearer test-token"}
OWNER_ID = str(uuid4())


async def _fake_require_site_scope(authorization: str | None = Header(None)) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return Principal(user_id=OWNER_ID, email="owner@example.com", all_sites=True, site_ids=[])


@pytest.fixture(autouse=True)
def override_site_scope():
    app.dependency_overrides[require_site_scope] = _fake_require_site_scope
    yield
    app.dependency_overrides.pop(require_site_scope, None)


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


def _create_rule(client: TestClient, **overrides) -> dict:
    body = {
        "condition": {"type": "volume_threshold", "bytes_threshold": 1000, "window_seconds": 60},
        **overrides,
    }
    resp = client.post("/rules", json=body, headers=AUTH_HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestRulesEndpoints:
    def test_created_rule_appears_in_list(self, client) -> None:
        created = _create_rule(client)

        list_resp = client.get("/rules", headers=AUTH_HEADERS)

        assert any(r["id"] == created["id"] for r in list_resp.json())

    def test_unsupported_condition_type_is_rejected(self, client) -> None:
        resp = client.post(
            "/rules",
            json={"condition": {"type": "anomaly_detection", "bytes_threshold": 1}},
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 422

    def test_update_replaces_enabled_flag(self, client) -> None:
        created = _create_rule(client)

        resp = client.patch(f"/rules/{created['id']}", json={"enabled": False}, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_delete_removes_the_rule(self, client) -> None:
        created = _create_rule(client)

        delete_resp = client.delete(f"/rules/{created['id']}", headers=AUTH_HEADERS)
        assert delete_resp.status_code == 204

        list_resp = client.get("/rules", headers=AUTH_HEADERS)
        assert all(r["id"] != created["id"] for r in list_resp.json())

    def test_deleting_unknown_rule_is_404(self, client) -> None:
        resp = client.delete(f"/rules/{uuid4()}", headers=AUTH_HEADERS)

        assert resp.status_code == 404


class TestEventsEndpoints:
    def test_events_list_is_empty_with_no_alerts(self, client) -> None:
        resp = client.get("/events", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.json() == []

    def test_unknown_event_flows_is_404(self, client) -> None:
        resp = client.get(f"/events/{uuid4()}/flows", headers=AUTH_HEADERS)

        assert resp.status_code == 404
