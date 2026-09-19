"""Contract tests for GET /summary, /top-talkers, /sites/status, /flows: asserts the
empty/reason and site_status response conventions from contracts/query-api.md.

Uses a fake ClickHouse client (protocol-compatible .query() call) so this runs without
Testcontainers; SQL-correctness against a real ClickHouse belongs in a
Testcontainers-backed CI job per the constitution's Testing Standards.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

import src.clickhouse as clickhouse_module
import src.sites_client as sites_client_module
from src.main import app

AUTH_HEADERS = {"Authorization": "Bearer test-token"}


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


def _patch_site_statuses(monkeypatch, statuses: dict[str, str]) -> None:
    async def _list() -> dict[str, str]:
        return statuses

    monkeypatch.setattr(sites_client_module, "list_site_statuses", _list)


class TestSummaryEndpoint:
    def test_returns_totals_and_application_breakdown(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[(1500, 10)])
        _patch_site_statuses(monkeypatch, {"site-1": "active"})

        resp = client.get("/summary?range=1h&sites=site-1", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["empty"] is False
        assert body["reason"] is None

    def test_no_traffic_sets_empty_and_reason(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[(0, 0)])
        _patch_site_statuses(monkeypatch, {})

        resp = client.get("/summary?range=1h&sites=site-1", headers=AUTH_HEADERS)

        body = resp.json()
        assert body["empty"] is True
        assert body["reason"] == "no_traffic"

    def test_missing_bearer_token_is_rejected(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[(0, 0)])

        resp = client.get("/summary?range=1h&sites=site-1")

        assert resp.status_code == 401

    def test_unsupported_range_is_rejected(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[(0, 0)])

        resp = client.get("/summary?range=9h&sites=site-1", headers=AUTH_HEADERS)

        assert resp.status_code == 422


class TestTopTalkersEndpoint:
    def test_returns_ranked_talkers(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[("10.0.0.6", 900), ("10.0.0.5", 100)])

        resp = client.get("/top-talkers?range=1h&sites=site-1&limit=5", headers=AUTH_HEADERS)

        body = resp.json()
        assert body["empty"] is False
        assert body["data"][0]["src_addr"] == "10.0.0.6"

    def test_empty_result_sets_reason(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[])

        resp = client.get("/top-talkers?range=1h&sites=site-1", headers=AUTH_HEADERS)

        body = resp.json()
        assert body["empty"] is True
        assert body["reason"] == "no_traffic"


class TestSiteStatusEndpoint:
    def test_returns_status_and_last_seen(self, client, monkeypatch) -> None:
        async def fake_get(self, url, **kwargs):
            class _Resp:
                def raise_for_status(self) -> None:
                    return None

                def json(self):
                    return [{"id": "site-1", "status": "stale", "last_seen_at": "2026-09-19T00:00:00Z"}]

            return _Resp()

        import httpx

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        resp = client.get("/sites/status", headers=AUTH_HEADERS)

        body = resp.json()
        assert body["data"][0]["status"] == "stale"


class TestFlowsEndpoint:
    def test_returns_flow_rows_with_expected_columns(self, client, monkeypatch) -> None:
        _patch_clickhouse(
            monkeypatch,
            rows=[
                (
                    "2026-09-19T18:00:00",
                    "site-1",
                    "10.0.0.5",
                    "10.0.0.1",
                    1234,
                    443,
                    6,
                    "HTTPS",
                    1000,
                    5,
                    "outbound",
                )
            ],
        )

        resp = client.get(
            "/flows?start=2026-09-19T00:00:00&end=2026-09-19T23:59:59",
            headers=AUTH_HEADERS,
        )

        body = resp.json()
        assert body["empty"] is False
        assert body["data"][0]["application"] == "HTTPS"

    def test_missing_required_time_range_is_rejected(self, client) -> None:
        resp = client.get("/flows", headers=AUTH_HEADERS)

        assert resp.status_code == 422
