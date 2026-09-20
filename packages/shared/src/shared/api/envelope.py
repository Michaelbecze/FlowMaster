"""Shared response-envelope types per contracts/query-api.md Response Conventions.

Every list/aggregate endpoint across query-api, alerting, and identity uses these so a
caller never has to infer "no data" vs "not retained anymore" from a bare empty array
(FR-018), and so incomplete site data is always flagged rather than silently under-reported
(FR-004).
"""

from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class EmptyReason(str, Enum):
    NO_TRAFFIC = "no_traffic"
    OUTSIDE_RETENTION = "outside_retention"


class SiteStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    NEVER_CONNECTED = "never_connected"


class Envelope(BaseModel, Generic[T]):
    data: T
    empty: bool = False
    reason: EmptyReason | None = None
    site_status: dict[str, SiteStatus] = {}

    @classmethod
    def of(
        cls,
        data: T,
        *,
        empty: bool = False,
        reason: EmptyReason | None = None,
        site_status: dict[str, SiteStatus] | None = None,
    ) -> "Envelope[T]":
        return cls(data=data, empty=empty, reason=reason, site_status=site_status or {})
