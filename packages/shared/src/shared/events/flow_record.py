"""FlowRecordEvent — the event published on the `flow-records.v1` topic.

Schema mirrors specs/001-enterprise-netflow-platform/contracts/event-flow-record.md
exactly. Producer: ingestion. Consumers: flow-writer, realtime, alerting.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION: Literal["1.0"] = "1.0"


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    UNKNOWN = "unknown"


class FlowRecordEvent(BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    site_id: str
    observed_at: datetime
    ingested_at: datetime
    src_addr: str
    dst_addr: str
    src_port: int = Field(ge=0, le=65535)
    dst_port: int = Field(ge=0, le=65535)
    protocol: int = Field(ge=0, le=255)
    application: str
    bytes: int = Field(ge=0)
    packets: int = Field(ge=0)
    direction: Direction

    def dedupe_key(self) -> tuple[str, str, str, int, str, int, int]:
        """At-least-once delivery requires idempotent consumers (contract §Guarantees)."""
        return (
            self.site_id,
            self.observed_at.isoformat(),
            self.src_addr,
            self.src_port,
            self.dst_addr,
            self.dst_port,
            self.protocol,
        )

    def model_dump_json_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def is_supported_schema_version(cls, version: str) -> bool:
        """Consumers MUST reject/quarantine unknown major versions (contract §Guarantees)."""
        return version.split(".")[0] == SCHEMA_VERSION.split(".")[0]
