import struct
import socket
from dataclasses import dataclass
from typing import List, Optional

# NetFlow v5 header: version, count, uptime, unix_secs, unix_nsecs, flow_seq, engine_type, engine_id, sampling
HEADER_FMT = "!HHIIIIBBH"
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 24 bytes

# NetFlow v5 record: pad1 (after dstport) and pad2 (final 2 bytes) are skipped with 'x'
RECORD_FMT = "!IIIHHIIIIHHxBBBHHBBxx"
RECORD_SIZE = struct.calcsize(RECORD_FMT)  # 48 bytes


@dataclass
class Flow:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int
    bytes: int
    packets: int
    duration_ms: int


@dataclass
class Packet:
    timestamp: float
    exporter_ip: str
    flows: List[Flow]


def parse(data: bytes, exporter_ip: str) -> Optional[Packet]:
    if len(data) < HEADER_SIZE:
        return None

    version, count, uptime, unix_secs, unix_nsecs, *_ = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    if version != 5:
        return None

    timestamp = unix_secs + unix_nsecs / 1e9
    flows = []

    for i in range(count):
        offset = HEADER_SIZE + i * RECORD_SIZE
        if offset + RECORD_SIZE > len(data):
            break

        (srcaddr, dstaddr, _nexthop, _in, _out,
         dPkts, dOctets, first, last,
         srcport, dstport, tcp_flags, prot, _tos,
         _src_as, _dst_as, _src_mask, _dst_mask) = struct.unpack(RECORD_FMT, data[offset:offset + RECORD_SIZE])

        flows.append(Flow(
            src_ip=socket.inet_ntoa(struct.pack("!I", srcaddr)),
            dst_ip=socket.inet_ntoa(struct.pack("!I", dstaddr)),
            src_port=srcport,
            dst_port=dstport,
            protocol=prot,
            bytes=dOctets,
            packets=dPkts,
            duration_ms=(last - first) & 0xFFFFFFFF,
        ))

    return Packet(timestamp=timestamp, exporter_ip=exporter_ip, flows=flows)
