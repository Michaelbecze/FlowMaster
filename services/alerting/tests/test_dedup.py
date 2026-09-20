"""De-dup test: a continuously-true condition does not create a duplicate AlertEvent
or notification (FR-013) — only a state transition (inactive->active or
active->inactive) does."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

import src.notifier as notifier_module
import src.volume_window as volume_window_module
from src import db as db_module
from src.evaluator import _evaluate_rule
from tests.fake_db import FakeDatabase, FakePool


@pytest.fixture
def db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture(autouse=True)
def patch_pool(monkeypatch, db: FakeDatabase):
    pool = FakePool(db)

    async def _get_pool():
        return pool

    monkeypatch.setattr(db_module, "get_pool", _get_pool)
    monkeypatch.setattr(notifier_module.db, "get_pool", _get_pool)


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(volume_window_module, "_redis", client)
    monkeypatch.setattr(volume_window_module, "get_redis", lambda: client)
    monkeypatch.setattr(notifier_module, "_redis", client)
    monkeypatch.setattr(notifier_module, "_get_redis", lambda: client)
    return client


@pytest.fixture(autouse=True)
def fake_owner_scope(monkeypatch):
    import src.evaluator as evaluator_module

    async def _all_sites(_user_id: str):
        return True, []

    monkeypatch.setattr(evaluator_module, "get_owner_scope", _all_sites)


def _make_rule(site_id: str, threshold: int = 1000) -> dict:
    return {
        "id": "rule-1",
        "owner_user_id": "user-1",
        "site_scope": site_id,
        "condition": {"type": "volume_threshold", "bytes_threshold": threshold, "window_seconds": 60},
        "notification_target": {},
    }


@pytest.mark.asyncio
class TestDedup:
    async def test_second_evaluation_while_condition_holds_does_not_create_a_new_event(
        self, db: FakeDatabase
    ) -> None:
        rule = _make_rule("site-1", threshold=1000)
        db.rules["rule-1"] = {
            "id": "rule-1", "owner_user_id": "user-1", "site_scope": "site-1",
            "condition_definition": "{}", "notification_target": "{}", "enabled": True,
            "created_at": None,
        }
        await volume_window_module.record_bytes("site-1", 2000)

        await _evaluate_rule(rule)
        await _evaluate_rule(rule)  # condition still true on the next tick

        assert len(db.events) == 1

    async def test_condition_resolving_and_retriggering_creates_a_second_event(
        self, db: FakeDatabase
    ) -> None:
        rule = _make_rule("site-1", threshold=1000)
        db.rules["rule-1"] = {
            "id": "rule-1", "owner_user_id": "user-1", "site_scope": "site-1",
            "condition_definition": "{}", "notification_target": "{}", "enabled": True,
            "created_at": None,
        }

        await volume_window_module.record_bytes("site-1", 2000)
        await _evaluate_rule(rule)  # triggers -> one open AlertEvent
        assert len(db.events) == 1
        first_event_id = next(iter(db.events))

        # Condition clears (no bytes recorded for "site-empty"): the next evaluation
        # against an empty window must resolve the open event, not leave it dangling.
        empty_rule = _make_rule("site-empty", threshold=1000)
        empty_rule["id"] = "rule-1"
        db.rules["rule-1"]["site_scope"] = "site-empty"
        await _evaluate_rule(empty_rule)

        assert db.events[first_event_id]["resolved_at"] is not None

        # Re-triggering after resolution creates a second, distinct event — this is
        # the "retriggering" half of FR-013, not just the de-dup half.
        await volume_window_module.record_bytes("site-empty", 2000)
        await _evaluate_rule(empty_rule)

        assert len(db.events) == 2
        assert set(db.events) != {first_event_id}  # a genuinely new event id exists

    async def test_below_threshold_never_creates_an_event(self, db: FakeDatabase) -> None:
        rule = _make_rule("site-1", threshold=1_000_000)
        db.rules["rule-1"] = {
            "id": "rule-1", "owner_user_id": "user-1", "site_scope": "site-1",
            "condition_definition": "{}", "notification_target": "{}", "enabled": True,
            "created_at": None,
        }
        await volume_window_module.record_bytes("site-1", 100)

        await _evaluate_rule(rule)

        assert len(db.events) == 0
