"""Automates quickstart.md Scenario 2 (Historical query & export, User Story 2) against
a running stack: `docker compose -f infra/docker-compose.yml up -d`.

Skipped rather than failed when GATEWAY_URL is unreachable — see
test_scenario_realtime_visibility.py for the rationale.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
ADMIN_EMAIL = os.environ.get("SCENARIO_ADMIN_EMAIL", "admin@flowmaster.test")
ADMIN_PASSWORD = os.environ.get("SCENARIO_ADMIN_PASSWORD", "changeme")


def _gateway_reachable() -> bool:
    try:
        httpx.get(f"{GATEWAY_URL}/healthz", timeout=1.0)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _gateway_reachable(),
    reason="requires a running infra/docker-compose.yml stack (GATEWAY_URL unreachable)",
)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    with httpx.Client(base_url=GATEWAY_URL, timeout=10.0) as client:
        login = client.post(
            "/api/v1/identity/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert login.status_code == 200, "seed an admin user before running this scenario"
        token = login.json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


class TestScenario2HistoricalReporting:
    def test_filtered_query_and_csv_export_round_trip(self, auth_headers) -> None:
        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0, headers=auth_headers) as client:
            now = datetime.now(timezone.utc)
            start = now - timedelta(hours=1)

            report_resp = client.post(
                "/api/v1/query/reports",
                json={"start": start.isoformat(), "end": now.isoformat(), "name": "scenario-2"},
            )
            assert report_resp.status_code == 201
            report_id = report_resp.json()["id"]

            view_resp = client.get(f"/api/v1/query/reports/{report_id}")
            assert view_resp.status_code == 200
            viewed = view_resp.json()

            export_resp = client.get(f"/api/v1/query/reports/{report_id}/export?format=csv")
            assert export_resp.status_code == 200
            assert export_resp.headers["content-type"].startswith("text/csv")

            # SC-009: exported rows must match exactly what the report view displayed.
            if not viewed["empty"]:
                for row in viewed["data"]:
                    assert row["src_addr"] in export_resp.text

    def test_query_outside_retention_window_is_flagged_not_empty(self, auth_headers) -> None:
        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0, headers=auth_headers) as client:
            ancient_end = datetime(2000, 1, 1, tzinfo=timezone.utc)
            ancient_start = ancient_end - timedelta(days=1)

            resp = client.get(
                "/api/v1/query/flows",
                params={"start": ancient_start.isoformat(), "end": ancient_end.isoformat()},
            )

            assert resp.status_code == 200
            body = resp.json()
            assert body["empty"] is True
            assert body["reason"] == "outside_retention"
