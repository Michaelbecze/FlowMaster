"""Automates quickstart.md Scenario 1 (Real-time visibility, User Story 1) against a
running stack: `docker compose -f infra/docker-compose.yml up -d`.

Requires the full stack (Gateway + all six services + infra) to be live, so it is
skipped rather than failed when GATEWAY_URL is unreachable — this is the
Testcontainers-class integration test the constitution's Testing Standards calls for
at a service boundary spanning the whole platform, not something a unit test can stand
in for. Run explicitly in CI once the compose stack is available:

    GATEWAY_URL=http://localhost:8080 pytest tests/integration/test_scenario_realtime_visibility.py
"""

from __future__ import annotations

import os
import socket
import struct
import time

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


def _send_synthetic_packet(exporter_ip_placeholder: str, netflow_host: str, netflow_port: int) -> None:
    """A generalized version of the existing project's test_flow.py smoke script."""
    now = int(time.time())
    header = struct.pack("!HHIIIIBBH", 5, 1, 60000, now, 0, 1, 0, 0, 0)
    record = struct.pack(
        "!IIIHHIIIIHHxBBBHHBBxx",
        struct.unpack("!I", socket.inet_aton("192.168.0.30"))[0],
        struct.unpack("!I", socket.inet_aton("8.8.8.8"))[0],
        struct.unpack("!I", socket.inet_aton("0.0.0.0"))[0],
        1,
        2,
        42,
        55296,
        59000,
        59900,
        54321,
        443,
        0x18,
        6,
        0,
        0,
        0,
        24,
        0,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(header + record, (netflow_host, netflow_port))
    finally:
        sock.close()


class TestScenario1RealtimeVisibility:
    def test_onboarded_site_traffic_appears_within_five_seconds(self) -> None:
        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0) as client:
            login = client.post(
                "/api/v1/identity/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
            assert login.status_code == 200, "seed an admin user before running this scenario"
            token = login.json()["session_token"]
            headers = {"Authorization": f"Bearer {token}"}

            site_resp = client.post(
                "/api/v1/identity/sites",
                json={"name": "scenario-1-site", "network_identity": "203.0.113.50"},
                headers=headers,
            )
            assert site_resp.status_code == 201
            site_id = site_resp.json()["id"]

            _send_synthetic_packet("203.0.113.50", netflow_host="localhost", netflow_port=2055)

            deadline = time.monotonic() + 5.0
            summary = None
            while time.monotonic() < deadline:
                resp = client.get(
                    f"/api/v1/query/summary?range=1h&sites={site_id}", headers=headers
                )
                summary = resp.json()
                if not summary["empty"]:
                    break
                time.sleep(0.5)

            assert summary is not None and not summary["empty"], (
                "SC-001: flow data must be reflected within 5 seconds"
            )

    def test_drilldown_returns_underlying_flow_records(self) -> None:
        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0) as client:
            login = client.post(
                "/api/v1/identity/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
            token = login.json()["session_token"]
            headers = {"Authorization": f"Bearer {token}"}

            now = time.time()
            resp = client.get(
                "/api/v1/query/flows",
                params={"start": now - 3600, "end": now + 60},
                headers=headers,
            )

            assert resp.status_code == 200
            assert "data" in resp.json()
