"""Malformed-packet counts and ingest lag (FR-014): the visible signal that ingest
volume is exceeding capacity, rather than a silent fall-behind."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IngestMetrics:
    packets_received: int = 0
    packets_malformed: int = 0
    flows_published: int = 0
    unattributed_flows: int = 0

    def record_received(self) -> None:
        self.packets_received += 1

    def record_malformed(self) -> None:
        self.packets_malformed += 1

    def record_published(self, count: int) -> None:
        self.flows_published += count

    def record_unattributed(self) -> None:
        self.unattributed_flows += 1

    def as_dict(self) -> dict[str, int]:
        return {
            "packets_received": self.packets_received,
            "packets_malformed": self.packets_malformed,
            "flows_published": self.flows_published,
            "unattributed_flows": self.unattributed_flows,
        }


metrics = IngestMetrics()
