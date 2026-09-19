"""Access-control test: a user scoped to one site cannot read another site's data via
/summary, /flows, or /reports (FR-009) — the server never trusts a client-supplied
site filter as authorization (contracts/query-api.md), even when the client asks for
an out-of-scope site explicitly."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from shared.authz import Principal, require_site_scope

import src.clickhouse as clickhouse_module
import src.db as db_module
import src.retention_client as retention_client_module
from src.main import app

ALLOWED_SITE = "site-allowed"
FORBIDDEN_SITE = "site-forbidden"

_FLOW_ROW = (
    "2026-09-19T18:00:00",
    FORBIDDEN_SITE,
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


async def _scoped_principal(authorization: str | None = None) -> Principal:
    return Principal(
        user_id="user-1", email="scoped@example.com", all_sites=False, site_ids=[ALLOWED_SITE]
    )


@pytest.fixture(autouse=True)
def override_site_scope():
    # See services/query-api/tests/contract/test_query_endpoints.py's
    # override_site_scope fixture for why this must be scoped to the test.
    app.dependency_overrides[require_site_scope] = _scoped_principal
    yield
    app.dependency_overrides.pop(require_site_scope, None)


@dataclass
class FakeQueryResult:
    result_rows: list[tuple]


class RecordingClickHouseClient:
    """Records the parameters every query was called with, so a test can assert the
    forbidden site never reached the query — not just that the response was empty."""

    def __init__(self, result_rows: list[tuple]) -> None:
        self._result_rows = result_rows
        self.calls: list[dict] = []

    async def query(self, query: str, parameters: dict | None = None) -> FakeQueryResult:
        self.calls.append(parameters or {})
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
            row = self._store.get(args[0])
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


@pytest.fixture
def fake_clickhouse(monkeypatch) -> RecordingClickHouseClient:
    fake = RecordingClickHouseClient([_FLOW_ROW])

    async def _get_client():
        return fake

    monkeypatch.setattr(clickhouse_module, "get_client", _get_client)
    return fake


@pytest.fixture(autouse=True)
def patch_postgres_and_retention(monkeypatch):
    fake_pool = FakePool()

    async def _get_pool():
        return fake_pool

    async def _get_retention_days():
        return 1

    monkeypatch.setattr(db_module, "get_pool", _get_pool)
    monkeypatch.setattr(retention_client_module, "get_retention_days", _get_retention_days)


AUTH_HEADERS = {"Authorization": "Bearer test-token"}


class TestSummaryScopeEnforcement:
    def test_forbidden_site_is_dropped_from_the_query(self, client, fake_clickhouse) -> None:
        resp = client.get(
            f"/summary?range=1h&sites={FORBIDDEN_SITE}", headers=AUTH_HEADERS
        )

        assert resp.status_code == 200
        for call in fake_clickhouse.calls:
            assert FORBIDDEN_SITE not in call.get("site_ids", [])

    def test_allowed_site_still_reaches_the_query(self, client, fake_clickhouse) -> None:
        resp = client.get(
            f"/summary?range=1h&sites={ALLOWED_SITE},{FORBIDDEN_SITE}", headers=AUTH_HEADERS
        )

        assert resp.status_code == 200
        assert any(ALLOWED_SITE in call.get("site_ids", []) for call in fake_clickhouse.calls)


class TestFlowsScopeEnforcement:
    def test_explicit_forbidden_site_id_returns_empty_not_data(self, client, fake_clickhouse) -> None:
        resp = client.get(
            "/flows",
            params={
                "start": "2026-09-19T00:00:00",
                "end": "2026-09-19T23:59:59",
                "site_id": FORBIDDEN_SITE,
            },
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["empty"] is True
        assert body["data"] == []
        # The forbidden site_id must never have reached ClickHouse.
        assert fake_clickhouse.calls == []

    def test_unscoped_query_is_restricted_to_allowed_sites(self, client, fake_clickhouse) -> None:
        resp = client.get(
            "/flows",
            params={"start": "2026-09-19T00:00:00", "end": "2026-09-19T23:59:59"},
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 200
        assert fake_clickhouse.calls[0]["allowed_site_ids"] == [ALLOWED_SITE]


class TestReportsScopeEnforcement:
    def test_creating_a_report_for_a_forbidden_site_is_rejected(self, client, fake_clickhouse) -> None:
        resp = client.post(
            "/reports",
            json={
                "start": "2026-09-19T00:00:00",
                "end": "2026-09-19T23:59:59",
                "site_id": FORBIDDEN_SITE,
            },
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 403
