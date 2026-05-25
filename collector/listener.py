import asyncio
import logging

from .netflow_v5 import parse

logger = logging.getLogger(__name__)


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, db, manager):
        self.db = db
        self.manager = manager

    def datagram_received(self, data: bytes, addr):
        import struct
        version = struct.unpack("!H", data[:2])[0] if len(data) >= 2 else -1
        logger.info("UDP packet from %s  len=%d  version=%d", addr[0], len(data), version)
        packet = parse(data, addr[0])
        if packet is None:
            logger.warning("Dropped packet from %s (version=%d, not v5 or malformed)", addr[0], version)
            return
        logger.info("Parsed %d flows from %s", len(packet.flows), addr[0])
        asyncio.ensure_future(self._handle(packet))

    async def _handle(self, packet):
        try:
            await self.db.insert_flows(packet.flows, packet.timestamp, packet.exporter_ip)
            await self.manager.broadcast_stats()
        except Exception:
            logger.exception("Error processing NetFlow packet")

    def error_received(self, exc):
        logger.error("NetFlow UDP error: %s", exc)


async def start(host: str, port: int, db, manager):
    loop = asyncio.get_event_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Protocol(db, manager),
        local_addr=(host, port),
    )
    logger.info("NetFlow v5 collector listening on %s:%d", host, port)
    return transport
