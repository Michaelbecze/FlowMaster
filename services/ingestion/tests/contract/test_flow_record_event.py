"""Contract test: events Ingestion builds must match FlowRecordEvent exactly
(contracts/event-flow-record.md), including the schema_version guarantee."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from shared.events.flow_record import Direction, FlowRecordEvent

from src.netflow_v5 import ParsedFlow
from src.producer import build_event


def _sample_flow() -> ParsedFlow:
    return ParsedFlow(
        src_addr="10.0.1.5",
        dst_addr="203.0.113.9",
        src_port=51321,
        dst_port=443,
        protocol=6,
        application="HTTPS",
        bytes=15420,
        packets=22,
        first_uptime_ms=100,
        last_uptime_ms=200,
    )


class TestBuildEvent:
    def test_event_matches_contract_schema(self) -> None:
        observed_at = datetime(2026, 9, 19, 18, 0, 0, tzinfo=timezone.utc)

        event = build_event(_sample_flow(), site_id="11111111-1111-1111-1111-111111111111", observed_at=observed_at)

        assert event.schema_version == "1.0"
        assert event.site_id == "11111111-1111-1111-1111-111111111111"
        assert event.observed_at == observed_at
        assert event.src_addr == "10.0.1.5"
        assert event.dst_addr == "203.0.113.9"
        assert event.src_port == 51321
        assert event.dst_port == 443
        assert event.protocol == 6
        assert event.application == "HTTPS"
        assert event.bytes == 15420
        assert event.packets == 22
        assert event.direction == Direction.UNKNOWN

    def test_serialized_bytes_round_trip_through_json(self) -> None:
        event = build_event(
            _sample_flow(), site_id="site-1", observed_at=datetime.now(timezone.utc)
        )

        payload = json.loads(event.model_dump_json_bytes())

        assert payload["schema_version"] == "1.0"
        assert set(payload) >= {
            "schema_version",
            "site_id",
            "observed_at",
            "ingested_at",
            "src_addr",
            "dst_addr",
            "src_port",
            "dst_port",
            "protocol",
            "application",
            "bytes",
            "packets",
            "direction",
        }

    def test_dedupe_key_is_stable_for_identical_flows(self) -> None:
        observed_at = datetime.now(timezone.utc)
        event_a = build_event(_sample_flow(), site_id="site-1", observed_at=observed_at)
        event_b = build_event(_sample_flow(), site_id="site-1", observed_at=observed_at)

        assert event_a.dedupe_key() == event_b.dedupe_key()

    def test_unknown_major_schema_version_is_rejected(self) -> None:
        assert FlowRecordEvent.is_supported_schema_version("2.0") is False
        assert FlowRecordEvent.is_supported_schema_version("1.3") is True
