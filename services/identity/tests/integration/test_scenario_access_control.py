"""Automates quickstart.md Scenario 3 (Access control & site onboarding, User Story 3)
against a running stack: `docker compose -f infra/docker-compose.yml up -d`.

Skipped rather than failed when GATEWAY_URL is unreachable — see
services/query-api/tests/integration/test_scenario_realtime_visibility.py for the
rationale.
"""

from __future__ import annotations

import os
import time
import uuid

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
def admin_headers() -> dict[str, str]:
    with httpx.Client(base_url=GATEWAY_URL, timeout=10.0) as client:
        login = client.post(
            "/api/v1/identity/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert login.status_code == 200, "seed an admin user before running this scenario"
        token = login.json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


class TestScenario3AccessControl:
    def test_scoped_user_cannot_see_a_second_sites_data(self, admin_headers) -> None:
        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0, headers=admin_headers) as admin:
            suffix = uuid.uuid4().hex[:8]
            # network_identity is unique per site (services/identity/migrations/0003_site.sql);
            # this test may run repeatedly against persistent infra, so it must be unique
            # per run too, not just the site *name*.
            octet_a = 1 + int(suffix[:4], 16) % 100
            octet_b = 101 + int(suffix[4:], 16) % 100

            site_a = admin.post(
                "/api/v1/identity/sites",
                json={"name": f"scenario-3-a-{suffix}", "network_identity": f"198.51.100.{octet_a}"},
            ).json()
            site_b = admin.post(
                "/api/v1/identity/sites",
                json={"name": f"scenario-3-b-{suffix}", "network_identity": f"198.51.100.{octet_b}"},
            ).json()

            scoped_email = f"scoped-{suffix}@flowmaster.test"
            invite = admin.post(
                "/api/v1/identity/users",
                json={"email": scoped_email, "password": "temp-password-123", "role": "viewer"},
            )
            assert invite.status_code == 201
            user_id = invite.json()["id"]

            roles_resp = admin.patch(
                f"/api/v1/identity/users/{user_id}/roles",
                json={"roles": [{"role": "viewer", "site_id": site_a["id"]}]},
            )
            assert roles_resp.status_code == 200

            login = admin.post(
                "/api/v1/identity/auth/login",
                json={"email": scoped_email, "password": "temp-password-123"},
            )
            scoped_headers = {"Authorization": f"Bearer {login.json()['session_token']}"}

        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0, headers=scoped_headers) as scoped:
            # Direct API call to the second site's data — not just the UI — per the
            # quickstart scenario's explicit instruction (FR-009).
            resp = scoped.get(f"/api/v1/query/summary?range=1h&sites={site_b['id']}")

            assert resp.status_code == 200
            body = resp.json()
            assert body["site_status"] == {}, "the out-of-scope site must not appear at all"

    def test_revoked_user_is_denied_on_next_request_without_restart(self, admin_headers) -> None:
        with httpx.Client(base_url=GATEWAY_URL, timeout=10.0, headers=admin_headers) as admin:
            suffix = uuid.uuid4().hex[:8]
            email = f"revoke-me-{suffix}@flowmaster.test"

            invite = admin.post(
                "/api/v1/identity/users",
                json={"email": email, "password": "temp-password-123"},
            )
            user_id = invite.json()["id"]

            login = admin.post(
                "/api/v1/identity/auth/login",
                json={"email": email, "password": "temp-password-123"},
            )
            token = login.json()["session_token"]

            whoami_before = admin.get(
                "/api/v1/identity/auth/whoami", headers={"Authorization": f"Bearer {token}"}
            )
            assert whoami_before.status_code == 200

            disable_resp = admin.patch(
                f"/api/v1/identity/users/{user_id}/status", json={"status": "disabled"}
            )
            assert disable_resp.status_code == 200

            whoami_after = admin.get(
                "/api/v1/identity/auth/whoami", headers={"Authorization": f"Bearer {token}"}
            )
            assert whoami_after.status_code == 401
