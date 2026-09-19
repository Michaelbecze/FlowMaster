"""Flow-Writer tests: idempotent dedupe on replay, and size/time-triggered batching.

Uses a fake ClickHouse client (protocol-compatible with the .insert() call
batch_writer.py makes) so this runs without Testcontainers — a Testcontainers-backed
Kafka+ClickHouse variant of the dedupe/insert path belongs in CI, per the constitution's
Testing Standards (service-level integration tests via real dependencies), but pure
buffering/dedupe logic does not need a live broker to verify.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from shared.events.flow_record import Direction, FlowRecordEvent
from src.batch_writer import BatchWriter
from src.consumer import DedupeCache, _handle_message


def _event(site_id: str = "site-1", src_port: int = 1000) -> FlowRecordEvent:
    now = datetime.now(timezone.utc)
    return FlowRecordEvent(
        site_id=site_id,
        observed_at=now,
        ingested_at=now,
        src_addr="10.0.0.1",
        dst_addr="10.0.0.2",
        src_port=src_port,
        dst_port=443,
        protocol=6,
        application="HTTPS",
        bytes=100,
        packets=1,
        direction=Direction.OUTBOUND,
    )


class FakeClickHouseClient:
    def __init__(self) -> None:
        self.inserted_batches: list[list] = []

    async def insert(self, table, rows, column_names) -> None:  # noqa: ANN001
        assert table == "flow_record"
        self.inserted_batches.append(rows)


@pytest.mark.asyncio
class TestBatchWriter:
    async def test_flush_writes_all_buffered_events(self, monkeypatch) -> None:
        fake_client = FakeClickHouseClient()
        monkeypatch.setattr("src.batch_writer.get_client", _fake_get_client(fake_client))

        writer = BatchWriter()
        await writer.add(_event(src_port=1))
        await writer.add(_event(src_port=2))
        flushed = await writer.flush()

        assert flushed == 2
        assert len(fake_client.inserted_batches) == 1
        assert len(fake_client.inserted_batches[0]) == 2

    async def test_flush_of_empty_buffer_is_a_noop(self, monkeypatch) -> None:
        fake_client = FakeClickHouseClient()
        monkeypatch.setattr("src.batch_writer.get_client", _fake_get_client(fake_client))

        writer = BatchWriter()
        flushed = await writer.flush()

        assert flushed == 0
        assert fake_client.inserted_batches == []

    async def test_max_size_triggers_immediate_flush(self, monkeypatch) -> None:
        fake_client = FakeClickHouseClient()
        monkeypatch.setattr("src.batch_writer.get_client", _fake_get_client(fake_client))

        writer = BatchWriter()
        writer._max_size = 2  # noqa: SLF001 — test-only override of the batching threshold
        await writer.add(_event(src_port=1))
        await writer.add(_event(src_port=2))
        await asyncio.sleep(0)  # let the add()-triggered flush task run

        assert len(fake_client.inserted_batches) == 1


def _fake_get_client(fake_client: FakeClickHouseClient):
    async def _get() -> FakeClickHouseClient:
        return fake_client

    return _get


@pytest.mark.asyncio
class TestDedupe:
    async def test_replayed_event_is_not_double_written(self) -> None:
        writer = _RecordingWriter()
        dedupe = DedupeCache()
        raw = _event().model_dump_json_bytes()

        await _handle_message(raw, writer, dedupe)
        await _handle_message(raw, writer, dedupe)  # simulated at-least-once redelivery

        assert len(writer.added) == 1

    async def test_distinct_events_are_both_written(self) -> None:
        writer = _RecordingWriter()
        dedupe = DedupeCache()

        await _handle_message(_event(src_port=1).model_dump_json_bytes(), writer, dedupe)
        await _handle_message(_event(src_port=2).model_dump_json_bytes(), writer, dedupe)

        assert len(writer.added) == 2

    async def test_unsupported_schema_version_is_quarantined(self) -> None:
        writer = _RecordingWriter()
        dedupe = DedupeCache()
        payload = _event().model_dump(mode="json")
        payload["schema_version"] = "2.0"
        raw = __import__("json").dumps(payload).encode("utf-8")

        await _handle_message(raw, writer, dedupe)

        assert writer.added == []


class _RecordingWriter:
    def __init__(self) -> None:
        self.added: list[FlowRecordEvent] = []

    async def add(self, event: FlowRecordEvent) -> None:
        self.added.append(event)
