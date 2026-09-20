"""Automates quickstart.md Scenario 4 (Alerting, User Story 4) against a running
stack: `docker compose -f infra/docker-compose.yml up -d`.

Skipped rather than failed when GATEWAY_URL is unreachable — see
services/query-api/tests/integration/test_scenario_realtime_visibility.py for the
rationale.
"""

from __future__ import annotations

import os
import socket
import struct
import time
import uuid

import httpx
import pytest

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
NETFLOW_HOST = os.environ.get("SCENARIO_NETFLOW_HOST", "localhost")
NETFLOW_PORT = int(os.environ.get("SCENARIO_NETFLOW_PORT", "2055"))
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


def _ip_to_int(ip: str) -> int:
    return struct.unpack("!I", socket.inet_aton(ip))[0]


def _send_synthetic_flow(octets: int) -> None:
    now = int(time.time())
    header = struct.pack("!HHIIIIBBH", 5, 1, 60000, now, 0, 1, 0, 0, 0)
    record = struct.pack(
        "!IIIHHIIIIHHxBBBHHBBxx",
        _ip_to_int("192.168.0.30"), _ip_to_int("8.8.8.8"), _ip_to_int("0.0.0.0"),
        1, 2, 10, octets, 59000, 59900, 54321, 443, 0x18, 6, 0, 0, 0, 24, 0,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(header + record, (NETFLOW_HOST, NETFLOW_PORT))
    finally:
        sock.close()


@pytest.fixture
def admin_headers() -> dict[str, str]:
    with httpx.Client(base_url=GATEWAY_URL, timeout=10.0) as client:
        login = client.post(
            "/api/v1/identity/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert login.status_code == 200, "seed an admin user before running this scenario"
        token = login.json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


class TestScenario4Alerting:
    def test_alert_fires_and_flow_data_is_retrievable(self, admin_headers) -> None:
        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0, headers=admin_headers) as client:
            suffix = uuid.uuid4().hex[:8]
            site = client.post(
                "/api/v1/identity/sites",
                json={"name": f"scenario-4-{suffix}", "network_identity": f"198.51.100.{1 + int(suffix, 16) % 250}"},
            ).json()

            rule = client.post(
                "/api/v1/alerting/rules",
                json={
                    "site_id": site["id"],
                    "condition": {
                        "type": "volume_threshold",
                        "bytes_threshold": 50_000,
                        "window_seconds": 60,
                    },
                },
            ).json()

            for _ in range(5):
                _send_synthetic_flow(octets=50_000)

            deadline = time.monotonic() + 60.0
            events: list[dict] = []
            while time.monotonic() < deadline:
                resp = client.get("/api/v1/alerting/events", params={"rule_id": rule["id"]})
                events = resp.json()
                if events:
                    break
                time.sleep(2)

            assert events, "SC-007: alert must fire within 60 seconds of the triggering condition"

            flows_resp = client.get(f"/api/v1/alerting/events/{events[0]['id']}/flows")
            assert flows_resp.status_code == 200

    def test_continued_traffic_does_not_duplicate_the_open_event(self, admin_headers) -> None:
        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0, headers=admin_headers) as client:
            suffix = uuid.uuid4().hex[:8]
            site = client.post(
                "/api/v1/identity/sites",
                json={"name": f"scenario-4b-{suffix}", "network_identity": f"198.51.101.{1 + int(suffix, 16) % 250}"},
            ).json()
            rule = client.post(
                "/api/v1/alerting/rules",
                json={
                    "site_id": site["id"],
                    "condition": {
                        "type": "volume_threshold",
                        "bytes_threshold": 50_000,
                        "window_seconds": 60,
                    },
                },
            ).json()

            for _ in range(5):
                _send_synthetic_flow(octets=50_000)
            time.sleep(20)  # let at least a couple of evaluation ticks pass
            for _ in range(5):
                _send_synthetic_flow(octets=50_000)  # condition remains continuously true
            time.sleep(20)

            events = client.get(
                "/api/v1/alerting/events", params={"rule_id": rule["id"]}
            ).json()

            open_events = [e for e in events if e["resolved_at"] is None]
            assert len(open_events) <= 1, "FR-013: no duplicate notification for an ongoing condition"
