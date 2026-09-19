"""Contract tests for POST /reports, GET /reports/{id}, GET /reports/{id}/export:
asserts exported output matches what GET /reports/{id} would show (SC-009), using a
fake ClickHouse client and a fake Postgres pool so this runs without Testcontainers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException, status
from fastapi.testclient import TestClient
from shared.authz import Principal, require_site_scope

import src.clickhouse as clickhouse_module
import src.db as db_module
import src.retention_client as retention_client_module
from src.main import app

AUTH_HEADERS = {"Authorization": "Bearer test-token"}


async def _fake_require_site_scope(authorization: str | None = Header(None)) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return Principal(user_id="user-1", email="test@example.com", all_sites=True, site_ids=[])


@pytest.fixture(autouse=True)
def override_site_scope():
    # See test_query_endpoints.py's override_site_scope fixture for why this must be
    # scoped to the test rather than a bare module-level assignment.
    app.dependency_overrides[require_site_scope] = _fake_require_site_scope
    yield
    app.dependency_overrides.pop(require_site_scope, None)


_FLOW_ROW = (
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


@dataclass
class FakeQueryResult:
    result_rows: list[tuple]


class FakeClickHouseClient:
    def __init__(self, result_rows: list[tuple]) -> None:
        self._result_rows = result_rows

    async def query(self, query: str, parameters: dict | None = None) -> FakeQueryResult:
        return FakeQueryResult(result_rows=self._result_rows)


class FakeConnection:
    def __init__(self, store: dict[str, dict]) -> None:
        self._store = store

    async def fetchrow(self, query: str, *args):
        if "INSERT INTO report" in query:
            report_id = str(uuid4())
            row = {
                "id": report_id,
                "name": args[2],
                "filter_definition": args[1],
                "created_at": datetime.now(timezone.utc),
            }
            self._store[report_id] = row
            return row
        if "SELECT filter_definition FROM report" in query:
            report_id = args[0]
            row = self._store.get(report_id)
            return {"filter_definition": row["filter_definition"]} if row else None
        raise AssertionError(f"unexpected query: {query}")


class FakePool:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection(self.store)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    fake_clickhouse = FakeClickHouseClient([_FLOW_ROW])
    fake_pool = FakePool()

    async def _get_clickhouse_client():
        return fake_clickhouse

    async def _get_pool():
        return fake_pool

    async def _get_retention_days():
        return 1

    monkeypatch.setattr(clickhouse_module, "get_client", _get_clickhouse_client)
    monkeypatch.setattr(db_module, "get_pool", _get_pool)
    monkeypatch.setattr(retention_client_module, "get_retention_days", _get_retention_days)
    yield fake_clickhouse


def _create_report(client: TestClient) -> dict:
    resp = client.post(
        "/reports",
        json={
            "start": "2026-09-19T00:00:00",
            "end": "2026-09-19T23:59:59",
            "name": "Daily HTTPS traffic",
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()


class TestCreateReport:
    def test_returns_saved_report_metadata(self, client) -> None:
        report = _create_report(client)

        assert report["name"] == "Daily HTTPS traffic"
        assert report["filter_definition"]["start"] == "2026-09-19T00:00:00"


class TestGetReport:
    def test_returns_current_results_for_the_saved_filter(self, client) -> None:
        report = _create_report(client)

        resp = client.get(f"/reports/{report['id']}", headers=AUTH_HEADERS)

        body = resp.json()
        assert body["empty"] is False
        assert body["data"][0]["application"] == "HTTPS"

    def test_unknown_report_id_is_404(self, client) -> None:
        resp = client.get(f"/reports/{uuid4()}", headers=AUTH_HEADERS)

        assert resp.status_code == 404


class TestExportReport:
    def test_csv_export_matches_what_get_report_shows(self, client) -> None:
        report = _create_report(client)

        view_resp = client.get(f"/reports/{report['id']}", headers=AUTH_HEADERS)
        export_resp = client.get(
            f"/reports/{report['id']}/export?format=csv", headers=AUTH_HEADERS
        )

        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"].startswith("text/csv")
        csv_body = export_resp.text
        viewed_row = view_resp.json()["data"][0]
        assert viewed_row["src_addr"] in csv_body
        assert viewed_row["application"] in csv_body

    def test_unsupported_format_is_rejected(self, client) -> None:
        report = _create_report(client)

        resp = client.get(f"/reports/{report['id']}/export?format=xlsx", headers=AUTH_HEADERS)

        assert resp.status_code == 422
