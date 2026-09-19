"""Kafka-compatible producer publishing validated flows as FlowRecordEvent to
flow-records.v1, partitioned by site_id (contracts/event-flow-record.md)."""

from __future__ import annotations

from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

from shared.events.flow_record import Direction, FlowRecordEvent

from .config import get_settings
from .netflow_v5 import ParsedFlow
from .metrics import metrics

TOPIC = "flow-records.v1"

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(bootstrap_servers=get_settings().kafka_brokers)
        await _producer.start()
    return _producer


async def close_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


def build_event(flow: ParsedFlow, site_id: str, observed_at: datetime) -> FlowRecordEvent:
    return FlowRecordEvent(
        site_id=site_id,
        observed_at=observed_at,
        ingested_at=datetime.now(timezone.utc),
        src_addr=flow.src_addr,
        dst_addr=flow.dst_addr,
        src_port=flow.src_port,
        dst_port=flow.dst_port,
        protocol=flow.protocol,
        application=flow.application,
        bytes=flow.bytes,
        packets=flow.packets,
        direction=Direction.UNKNOWN,
    )


async def publish_flow(event: FlowRecordEvent) -> None:
    """Non-blocking relative to the UDP listener socket (constitution Principle IV):
    publishing to the event stream, never a synchronous downstream write."""
    producer = await get_producer()
    await producer.send_and_wait(
        TOPIC,
        value=event.model_dump_json_bytes(),
        key=event.site_id.encode("utf-8"),
    )
    metrics.record_published(1)
