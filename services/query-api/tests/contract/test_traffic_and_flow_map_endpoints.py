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

    def test_naive_bucket_is_serialized_with_an_explicit_utc_offset(
        self, client, monkeypatch
    ) -> None:
        """Regression: `timestamp` is a DateTime64 with no zone, so the driver returns
        a *naive* datetime (the tests above pass an aware one, which is why this got
        through). Serialized bare it lost the offset, and the dashboard — which parses
        this value straight back into the flow drill-down window — read it as local
        time, so every non-UTC browser drilled into a window hours from the traffic and
        got an empty flow list."""
        naive_utc = datetime(2026, 9, 20, 14, 30, 0)
        _patch_clickhouse(monkeypatch, rows=[(naive_utc, 1000, 10)])

        resp = client.get("/traffic-over-time?range=1h&sites=site-1", headers=AUTH_HEADERS)

        bucket = resp.json()["data"][0]["bucket"]
        # Must carry a zone designator, and must denote the same instant it was stored at.
        assert bucket.endswith("+00:00") or bucket.endswith("Z"), bucket
        assert datetime.fromisoformat(bucket) == naive_utc.replace(tzinfo=timezone.utc)

    def test_aware_bucket_keeps_its_instant(self, client, monkeypatch) -> None:
        """The driver returns aware datetimes under some versions/settings; those must
        pass through as the same instant rather than being relabeled as UTC."""
        aware = datetime(2026, 9, 20, 14, 30, 0, tzinfo=timezone.utc)
        _patch_clickhouse(monkeypatch, rows=[(aware, 1000, 10)])

        resp = client.get("/traffic-over-time?range=1h&sites=site-1", headers=AUTH_HEADERS)

        assert datetime.fromisoformat(resp.json()["data"][0]["bucket"]) == aware


class TestFlowMap:
    def test_both_directions_of_a_conversation_are_kept_separate(self, client, monkeypatch) -> None:
        """A->B and B->A are two different measurements and stay two links.

        These used to be summed into one link to keep ECharts' sankey acyclic, which
        both merged opposing volumes into a single number and could draw the surviving
        link backwards (the direction came from sorting the addresses, not from the
        traffic). The chart is now a strict two-column source -> destination diagram,
        where an address on each side is a distinct node, so no cycle is representable
        and the real directions can be reported as measured."""
        _patch_clickhouse(
            monkeypatch,
            rows=[
                ("10.0.0.1", "10.0.0.2", 500),
                ("10.0.0.2", "10.0.0.1", 300),
            ],
        )

        resp = client.get("/flow-map?range=1h&sites=site-1", headers=AUTH_HEADERS)

        links = resp.json()["data"]["links"]
        assert len(links) == 2
        assert {(link["source"], link["target"], link["value"]) for link in links} == {
            ("10.0.0.1", "10.0.0.2", 500),
            ("10.0.0.2", "10.0.0.1", 300),
        }

    def test_link_direction_matches_the_measured_flow(self, client, monkeypatch) -> None:
        """Regression: keying on sorted((src, dst)) emitted the link in address-sort
        order, so a flow could be drawn pointing the opposite way to the traffic it
        represented.

        The source here must sort *after* the destination for this to bite — with any
        pair that already happens to be in sort order, the old code produced the right
        answer by luck and the test would pass against the bug it is meant to catch."""
        # "203.0.113.20" > "203.0.113.100" as strings, so sort order reverses this pair.
        _patch_clickhouse(monkeypatch, rows=[("203.0.113.20", "203.0.113.100", 900)])

        resp = client.get("/flow-map?range=1h&sites=site-1", headers=AUTH_HEADERS)

        link = resp.json()["data"]["links"][0]
        assert link["source"] == "203.0.113.20"
        assert link["target"] == "203.0.113.100"

    def test_empty_result_sets_reason(self, client, monkeypatch) -> None:
        _patch_clickhouse(monkeypatch, rows=[])

        resp = client.get("/flow-map?range=1h&sites=site-1", headers=AUTH_HEADERS)

        body = resp.json()
        assert body["empty"] is True
        assert body["reason"] == "no_traffic"
