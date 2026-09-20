"""Realtime tests: rolling-aggregate updates and the active -> stale transition after
the configured threshold, against a fake Redis (fakeredis) so this runs without a live
cluster — see test_batch_writer.py for why pure aggregation logic doesn't need
Testcontainers to verify correctness."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import fakeredis.aioredis
import pytest

import src.aggregator as aggregator_module
from shared.events.flow_record import Direction, FlowRecordEvent
from src import staleness as staleness_module
from src.aggregator import get_site_summary, record_event


def _event(site_id: str, src_addr: str = "10.0.0.5", bytes_: int = 1000) -> FlowRecordEvent:
    now = datetime.now(timezone.utc)
    return FlowRecordEvent(
        site_id=site_id,
        observed_at=now,
        ingested_at=now,
        src_addr=src_addr,
        dst_addr="10.0.0.1",
        src_port=1234,
        dst_port=443,
        protocol=6,
        application="HTTPS",
        bytes=bytes_,
        packets=5,
        direction=Direction.OUTBOUND,
    )


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(aggregator_module, "_redis", client)
    monkeypatch.setattr(aggregator_module, "get_redis", lambda: client)
    yield client


@pytest.mark.asyncio
class TestAggregateCache:
    async def test_summary_aggregates_bytes_and_protocol_mix(self) -> None:
        await record_event(_event("site-1", src_addr="10.0.0.5", bytes_=1000))
        await record_event(_event("site-1", src_addr="10.0.0.6", bytes_=500))

        summary = await get_site_summary("site-1")

        assert summary["total_bytes"] == 1500
        assert summary["protocol_mix"]["HTTPS"] == 1500

    async def test_top_talkers_ranks_by_bytes_descending(self) -> None:
        await record_event(_event("site-1", src_addr="10.0.0.5", bytes_=100))
        await record_event(_event("site-1", src_addr="10.0.0.6", bytes_=900))

        summary = await get_site_summary("site-1")

        assert summary["top_talkers"][0]["src_addr"] == "10.0.0.6"

    async def test_events_outside_the_window_are_trimmed(self) -> None:
        old_ts = time.time() - 10_000  # far outside the default 300s window
        await record_event(_event("site-1", bytes_=777), seen_at=old_ts)

        summary = await get_site_summary("site-1")

        assert summary["total_bytes"] == 0

    async def test_sites_with_no_events_have_an_empty_summary(self) -> None:
        summary = await get_site_summary("never-seen-site")

        assert summary["total_bytes"] == 0
        assert summary["top_talkers"] == []


@pytest.mark.asyncio
class TestStaleness:
    async def _reset_state(self) -> None:
        staleness_module._last_seen.clear()
        staleness_module._last_reported_status.clear()
        staleness_module._last_identity_call.clear()

    async def test_site_transitions_to_stale_after_threshold(self, monkeypatch) -> None:
        import asyncio
        import dataclasses

        await self._reset_state()
        events: list[tuple[str, str]] = []

        async def fake_set_status(site_id: str, status: str) -> None:
            events.append((site_id, status))

        monkeypatch.setattr(staleness_module, "_set_status", fake_set_status)
        monkeypatch.setattr(staleness_module, "_report_seen", _noop)

        fast_settings = dataclasses.replace(
            staleness_module.get_settings(),
            staleness_sweep_interval_seconds=0.01,
            stale_after_seconds=1,
        )
        monkeypatch.setattr(staleness_module, "get_settings", lambda: fast_settings)
        staleness_module._last_seen["site-1"] = time.time() - fast_settings.stale_after_seconds - 1

        async def on_status_changed(site_id: str, status: str) -> None:
            events.append((f"broadcast:{site_id}", status))

        task = asyncio.ensure_future(staleness_module.run_staleness_sweep(on_status_changed))
        await asyncio.sleep(fast_settings.staleness_sweep_interval_seconds + 0.05)
        task.cancel()

        assert ("site-1", "stale") in events
        assert ("broadcast:site-1", "stale") in events

    async def test_note_site_seen_clears_stale_status(self, monkeypatch) -> None:
        await self._reset_state()
        calls: list[tuple[str, str]] = []

        async def fake_set_status(site_id: str, status: str) -> None:
            calls.append((site_id, status))

        monkeypatch.setattr(staleness_module, "_set_status", fake_set_status)
        monkeypatch.setattr(staleness_module, "_report_seen", _noop)
        staleness_module._last_reported_status["site-1"] = "stale"

        await staleness_module.note_site_seen("site-1")

        assert ("site-1", "active") in calls


async def _noop(*args, **kwargs) -> None:
    return None
