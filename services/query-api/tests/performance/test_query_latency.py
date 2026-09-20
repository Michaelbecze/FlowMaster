"""Query-performance test: a filtered query over the retention window must return in
under 3 seconds for 95% of queries (SC-003).

Requires a reachable ClickHouse (the same instance infra/docker-compose.yml brings up);
skipped rather than failed when unreachable, per the same rationale as
tests/integration/test_scenario_realtime_visibility.py. Seeds a scaled-down synthetic
dataset (SEED_ROWS) rather than 30 real days of production volume — this asserts query
*shape* performance (indexed range + equality filters), not absolute production scale,
which belongs in a dedicated load-test environment.
"""

from __future__ import annotations

import os
import random
import statistics
import time
from datetime import datetime, timedelta, timezone

import clickhouse_connect
import pytest

# Deliberately a separate env var from CLICKHOUSE_URL: conftest.py sets that to a
# credential-less dummy value for the contract tests' mocked dependencies, which would
# otherwise leak into this test and fail auth against a real, password-protected instance.
CLICKHOUSE_URL = os.environ.get(
    "PERF_TEST_CLICKHOUSE_URL", "http://default:flowmaster@localhost:8123"
)
SEED_ROWS = int(os.environ.get("PERF_TEST_SEED_ROWS", "50000"))
SEED_SITE_ID = "perf-test-site"
P95_BUDGET_SECONDS = 3.0
SAMPLE_QUERIES = 20


def _clickhouse_reachable() -> bool:
    try:
        client = clickhouse_connect.get_client(dsn=CLICKHOUSE_URL)
        client.command("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _clickhouse_reachable(),
    reason="requires a running infra/docker-compose.yml ClickHouse (CLICKHOUSE_URL unreachable)",
)


@pytest.fixture(scope="module")
def seeded_client():
    client = clickhouse_connect.get_client(dsn=CLICKHOUSE_URL)
    client.command(f"DELETE FROM flow_record WHERE site_id = '{SEED_SITE_ID}'")

    now = datetime.now(timezone.utc)
    columns = [
        "timestamp",
        "site_id",
        "src_addr",
        "dst_addr",
        "src_port",
        "dst_port",
        "protocol",
        "application",
        "bytes",
        "packets",
        "direction",
        "ingested_at",
    ]
    rows = []
    for i in range(SEED_ROWS):
        ts = now - timedelta(seconds=random.randint(0, 30 * 24 * 3600))
        rows.append(
            [
                ts,
                SEED_SITE_ID,
                f"10.0.{i % 255}.{(i * 7) % 255}",
                "8.8.8.8",
                random.randint(1024, 65535),
                443,
                6,
                "HTTPS",
                random.randint(100, 100_000),
                random.randint(1, 100),
                "outbound",
                ts,
            ]
        )
    client.insert("flow_record", rows, column_names=columns)
    yield client
    client.command(f"DELETE FROM flow_record WHERE site_id = '{SEED_SITE_ID}'")


class TestQueryLatency:
    def test_p95_filtered_query_latency_under_budget(self, seeded_client) -> None:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        durations = []
        for _ in range(SAMPLE_QUERIES):
            t0 = time.perf_counter()
            seeded_client.query(
                "SELECT src_addr, sum(bytes) AS total_bytes FROM flow_record "
                "WHERE site_id = {site_id:String} AND timestamp >= {start:DateTime64} "
                "AND timestamp <= {end:DateTime64} GROUP BY src_addr "
                "ORDER BY total_bytes DESC LIMIT 100",
                parameters={"site_id": SEED_SITE_ID, "start": start, "end": now},
            )
            durations.append(time.perf_counter() - t0)

        p95 = statistics.quantiles(durations, n=100)[94]
        assert p95 < P95_BUDGET_SECONDS, (
            f"p95 latency {p95:.3f}s exceeds the {P95_BUDGET_SECONDS}s budget (SC-003)"
        )
