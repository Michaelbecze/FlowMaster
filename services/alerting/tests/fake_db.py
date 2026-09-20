"""A minimal in-memory stand-in for alerting's PostgreSQL schema (alert_rule,
alert_event), used by the contract tests so they run without Testcontainers — see
services/identity/tests/fake_db.py for the same rationale."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone


def _new_id() -> str:
    return str(uuid.uuid4())


class FakeDatabase:
    def __init__(self) -> None:
        self.rules: dict[str, dict] = {}
        self.events: dict[str, dict] = {}


class FakeConnection:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    async def fetchrow(self, query: str, *args):
        q = " ".join(query.split())

        if q.startswith("SELECT owner_user_id FROM alert_rule WHERE id"):
            rule = self.db.rules.get(args[0])
            return {"owner_user_id": rule["owner_user_id"]} if rule else None

        if q.startswith("INSERT INTO alert_rule"):
            owner_user_id, site_scope, condition_definition, notification_target, enabled = args
            rule_id = _new_id()
            row = {
                "id": rule_id, "owner_user_id": owner_user_id, "site_scope": site_scope,
                "condition_definition": condition_definition, "notification_target": notification_target,
                "enabled": enabled, "created_at": datetime.now(timezone.utc),
            }
            self.db.rules[rule_id] = row
            return dict(row)

        if q.startswith("UPDATE alert_rule SET"):
            rule_id, condition_definition, notification_target, enabled = args
            rule = self.db.rules.get(rule_id)
            if not rule:
                return None
            if condition_definition is not None:
                rule["condition_definition"] = condition_definition
            if notification_target is not None:
                rule["notification_target"] = notification_target
            if enabled is not None:
                rule["enabled"] = enabled
            return dict(rule)

        if q.startswith("INSERT INTO alert_event"):
            alert_rule_id, triggering_flow_reference = args
            event_id = _new_id()
            self.db.events[event_id] = {
                "id": event_id, "alert_rule_id": alert_rule_id,
                "triggering_flow_reference": triggering_flow_reference,
                "triggered_at": datetime.now(timezone.utc), "resolved_at": None,
            }
            return {"id": event_id}

        if q.startswith("SELECT ae.triggered_at, ae.triggering_flow_reference"):
            event_id, owner_user_id = args
            event = self.db.events.get(event_id)
            if not event:
                return None
            rule = self.db.rules.get(event["alert_rule_id"])
            if not rule or rule["owner_user_id"] != owner_user_id:
                return None
            return {
                "triggered_at": event["triggered_at"],
                "triggering_flow_reference": event["triggering_flow_reference"],
            }

        raise AssertionError(f"FakeConnection.fetchrow: unrecognized query: {q}")

    async def fetch(self, query: str, *args):
        q = " ".join(query.split())

        if q.startswith("SELECT id, owner_user_id, site_scope, condition_definition, "
                         "notification_target, enabled, created_at FROM alert_rule WHERE owner_user_id"):
            return [dict(r) for r in self.db.rules.values() if r["owner_user_id"] == args[0]]

        if q.startswith("SELECT id, owner_user_id, site_scope, condition_definition, "
                         "notification_target FROM alert_rule WHERE enabled"):
            return [dict(r) for r in self.db.rules.values() if r["enabled"]]

        if "FROM alert_event ae" in q and "JOIN alert_rule ar" in q:
            owner_user_id = args[0]
            rule_id = args[1] if len(args) > 1 and "ae.alert_rule_id = $2" in q else None
            results = []
            for e in self.db.events.values():
                rule = self.db.rules.get(e["alert_rule_id"])
                if not rule or rule["owner_user_id"] != owner_user_id:
                    continue
                if rule_id and e["alert_rule_id"] != rule_id:
                    continue
                results.append(dict(e))
            results.sort(key=lambda e: e["triggered_at"], reverse=True)
            return results

        raise AssertionError(f"FakeConnection.fetch: unrecognized query: {q}")

    async def execute(self, query: str, *args):
        q = " ".join(query.split())

        if q.startswith("DELETE FROM alert_rule WHERE id"):
            rule_id, owner_user_id = args
            rule = self.db.rules.get(rule_id)
            if rule and rule["owner_user_id"] == owner_user_id:
                del self.db.rules[rule_id]
                return "DELETE 1"
            return "DELETE 0"

        if q.startswith("UPDATE alert_event SET resolved_at"):
            event_id = args[0]
            event = self.db.events.get(event_id)
            if event and event["resolved_at"] is None:
                event["resolved_at"] = datetime.now(timezone.utc)
                return "UPDATE 1"
            return "UPDATE 0"

        raise AssertionError(f"FakeConnection.execute: unrecognized query: {q}")


class FakePool:
    def __init__(self, db: FakeDatabase | None = None) -> None:
        self.db = db or FakeDatabase()

    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection(self.db)
