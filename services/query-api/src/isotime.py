"""Serializing ClickHouse timestamps as unambiguous instants.

The `flow_record` table stores `timestamp` as `DateTime64(3)`, which carries no
timezone, so the driver hands back a *naive* datetime that is really UTC. Serialized
as-is that becomes "2026-09-20T14:30:00" — no offset — and ECMAScript's Date parser
reads an offset-less date-time as **local** time, not UTC.

That is not a cosmetic difference. The dashboard builds its flow drill-down window by
parsing this value (`new Date(bucket)` in TrafficChart/Dashboard), so on any browser
not set to UTC the window landed hours away from the traffic it was derived from and
the drill-down came back empty — while "View flows (last 5m)", which builds its window
from `Date.now()` and never round-trips through this string, kept working.

Anything leaving this service with a time in it goes through here.
"""

from __future__ import annotations

from datetime import datetime, timezone


def to_utc_iso(value: datetime) -> str:
    """Render a ClickHouse datetime as an explicit UTC instant.

    Correct whether the driver returns naive datetimes (assumed UTC, matching the
    column's storage) or timezone-aware ones — the driver's behavior here depends on
    its version and the `apply_server_timezone` setting, so neither is assumed.
    """
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.isoformat()
