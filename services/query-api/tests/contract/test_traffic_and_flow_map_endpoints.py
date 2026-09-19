"""Contract tests for GET /traffic-over-time and GET /flow-map — the bucketed traffic
chart and Sankey flow-map endpoints restoring the single-process dashboard's
visualizations for the enterprise dashboard's per-site view."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from fastapi import Header, HTTPException, status
from fastapi.testclient import TestClient
from shared.authz import Principal, require_site_scope

import src.clickhouse as clickhouse_module
from src.main import app

AUTH_HEADERS = {"Authorization": "Bearer test-token"}


async def _fake_require_site_scope(authorization: str | None = Header(None)) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return Principal(user_id="user-1", email="test@example.com", all_sites=True, site_ids=[])


@pytest.fixture(autouse=True)
def override_site_scope():
    app.dependency_overrides[require_site_scope] = _fake_require_site_scope
    yield
    app.dependency_overrides.pop(require_site_scope, None)


@dataclass
class FakeQueryResult:
    result_rows: list[tuple]


class FakeClickHouseClient:
    def __init__(self, result_rows: list[tuple]) -> None:
        self._result_rows = result_rows

    async def query(self, query: str, parameters: dict | None = None) -> FakeQueryResult:
        return FakeQueryResult(result_rows=self._result_rows)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _patch_clickhouse(monkeypatch, rows: list[tuple]) -> None:
    fake = FakeClickHouseClient(rows)

    async def _get_client():
        return fake

    monkeypatch.setattr(clickhouse_module, "get_client", _get_client)


class TestTrafficOverTime:
    def test_returns_buckets_in_order(self, client, monkeypatch) -> None:
        now = datetime.now(timezone.utc)
        _patch_clickhouse(monkeypatch, rows=[(now, 1000, 10), (now, 2000, 20)])

        resp = client.get("/traffic-over-time?range=1h&sites=site-1", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["empty"] is False
        assert body["data"][0]["total_bytes"] == 1000

    def test_empty_result_sets_reason(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[])

        resp = client.get("/traffic-over-time?range=1h&sites=site-1", headers=AUTH_HEADERS)

        body = resp.json()
        assert body["empty"] is True
        assert body["reason"] == "no_traffic"

    def test_missing_bearer_token_is_rejected(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[])

        resp = client.get("/traffic-over-time?range=1h&sites=site-1")

        assert resp.status_code == 401


class TestFlowMap:
    def test_bidirectional_pairs_are_merged_into_one_link(self, client, monkeypatch) -> None:
        # A->B and B->A both present: must collapse to a single link, since ECharts'
        # sankey series throws on any cycle (see flow_map.py's comment).
        _patch_clickhouse(
            monkeypatch,
            rows=[
                ("10.0.0.1", "10.0.0.2", 500),
                ("10.0.0.2", "10.0.0.1", 300),
            ],
        )

        resp = client.get("/flow-map?range=1h&sites=site-1", headers=AUTH_HEADERS)

        body = resp.json()
        assert len(body["data"]["links"]) == 1
        assert body["data"]["links"][0]["value"] == 800
        assert len(body["data"]["nodes"]) == 2

    def test_empty_result_sets_reason(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[])

        resp = client.get("/flow-map?range=1h&sites=site-1", headers=AUTH_HEADERS)

        body = resp.json()
        assert body["empty"] is True
        assert body["reason"] == "no_traffic"
