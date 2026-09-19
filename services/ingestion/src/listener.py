"""Asyncio UDP NetFlow v5 listener — non-blocking per constitution Principle IV.

Generalized from the existing project's collector/listener.py: each datagram is handed
to an async task immediately so a slow attribution/publish call never stalls the socket.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .attribution import attribute_site
from .config import get_settings
from .metrics import metrics
from .netflow_v5 import MalformedPacketError, parse_packet
from .producer import build_event, publish_flow

logger = logging.getLogger(__name__)


class NetflowProtocol(asyncio.DatagramProtocol):
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        metrics.record_received()
        # Schedule processing as a task rather than awaiting inline: the listener must
        # keep draining the socket even while attribution/publish is in flight.
        asyncio.create_task(_process_packet(data, exporter_ip=addr[0]))

    def error_received(self, exc: Exception) -> None:
        logger.warning("UDP listener error: %s", exc)


async def _process_packet(data: bytes, exporter_ip: str) -> None:
    try:
        parsed = parse_packet(data)
    except MalformedPacketError as exc:
        metrics.record_malformed()
        logger.info("rejected malformed packet from %s: %s", exporter_ip, exc)
        return

    site_id = await attribute_site(exporter_ip)
    if site_id is None:
        logger.info("no site onboarded for exporter %s; dropping %d flows", exporter_ip, len(parsed.flows))
        return

    observed_at = datetime.fromtimestamp(parsed.unix_secs, tz=timezone.utc)
    for flow in parsed.flows:
        event = build_event(flow, site_id=site_id, observed_at=observed_at)
        await publish_flow(event)


async def start_listener() -> asyncio.DatagramTransport:
    settings = get_settings()
    loop = asyncio.get_running_loop()
    transport, _protocol = await loop.create_datagram_endpoint(
        NetflowProtocol,
        local_addr=(settings.netflow_host, settings.netflow_port),
    )
    logger.info("NetFlow v5 listener bound to %s:%d/udp", settings.netflow_host, settings.netflow_port)
    return transport
