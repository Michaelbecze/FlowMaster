"""NetFlow v5 binary packet parser — defensive by construction.

The Ingestion service accepts unauthenticated UDP packets from the network
(constitution Technology & Security Constraints); every unpack here is length-validated
first, and a malformed/truncated packet raises MalformedPacketError rather than an
unhandled struct.error, so one bad packet never affects any other (FR-015).
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

HEADER_FMT = "!HHIIIIBBH"
HEADER_LEN = struct.calcsize(HEADER_FMT)  # 24 bytes

RECORD_FMT = "!IIIHHIIIIHHxBBBHHBBxx"
RECORD_LEN = struct.calcsize(RECORD_FMT)  # 48 bytes

_PORT_APPLICATIONS = {
    20: "FTP",
    21: "FTP",
    22: "SSH",
    23: "TELNET",
    25: "SMTP",
    53: "DNS",
    67: "DHCP",
    68: "DHCP",
    80: "HTTP",
    110: "POP3",
    123: "NTP",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    3306: "MYSQL",
    3389: "RDP",
    5432: "POSTGRESQL",
    8080: "HTTP-ALT",
}


class MalformedPacketError(ValueError):
    """Raised for a truncated or structurally invalid NetFlow v5 packet."""


@dataclass(frozen=True)
class ParsedFlow:
    src_addr: str
    dst_addr: str
    src_port: int
    dst_port: int
    protocol: int
    application: str
    bytes: int
    packets: int
    first_uptime_ms: int
    last_uptime_ms: int


@dataclass(frozen=True)
class ParsedPacket:
    version: int
    count: int
    sys_uptime_ms: int
    unix_secs: int
    unix_nsecs: int
    flow_sequence: int
    flows: list[ParsedFlow]


def _addr_to_str(raw: int) -> str:
    return socket.inet_ntoa(struct.pack("!I", raw))


def guess_application(dst_port: int, src_port: int) -> str:
    return _PORT_APPLICATIONS.get(dst_port) or _PORT_APPLICATIONS.get(src_port) or "OTHER"


def parse_packet(data: bytes) -> ParsedPacket:
    """Parse one NetFlow v5 UDP payload.

    Raises MalformedPacketError for any structural problem — never lets a
    struct.error or IndexError propagate and crash the caller (FR-015).
    """
    if len(data) < HEADER_LEN:
        raise MalformedPacketError(
            f"packet too short for header: {len(data)} < {HEADER_LEN} bytes"
        )

    try:
        (
            version,
            count,
            sys_uptime_ms,
            unix_secs,
            unix_nsecs,
            flow_sequence,
            _engine_type,
            _engine_id,
            _sampling_interval,
        ) = struct.unpack(HEADER_FMT, data[:HEADER_LEN])
    except struct.error as exc:
        raise MalformedPacketError(f"failed to unpack header: {exc}") from exc

    if version != 5:
        raise MalformedPacketError(f"unsupported NetFlow version: {version}")

    expected_len = HEADER_LEN + count * RECORD_LEN
    if len(data) < expected_len:
        raise MalformedPacketError(
            f"declared count {count} needs {expected_len} bytes, got {len(data)}"
        )

    flows: list[ParsedFlow] = []
    offset = HEADER_LEN
    for _ in range(count):
        chunk = data[offset : offset + RECORD_LEN]
        try:
            (
                src_raw,
                dst_raw,
                _nexthop_raw,
                _input_if,
                _output_if,
                packets,
                octets,
                first_ms,
                last_ms,
                src_port,
                dst_port,
                _tcp_flags,
                protocol,
                _tos,
                _src_as,
                _dst_as,
                _src_mask,
                _dst_mask,
            ) = struct.unpack(RECORD_FMT, chunk)
        except struct.error as exc:
            raise MalformedPacketError(f"failed to unpack record at offset {offset}: {exc}") from exc

        flows.append(
            ParsedFlow(
                src_addr=_addr_to_str(src_raw),
                dst_addr=_addr_to_str(dst_raw),
                src_port=src_port,
                dst_port=dst_port,
                protocol=protocol,
                application=guess_application(dst_port, src_port),
                bytes=octets,
                packets=packets,
                first_uptime_ms=first_ms,
                last_uptime_ms=last_ms,
            )
        )
        offset += RECORD_LEN

    return ParsedPacket(
        version=version,
        count=count,
        sys_uptime_ms=sys_uptime_ms,
        unix_secs=unix_secs,
        unix_nsecs=unix_nsecs,
        flow_sequence=flow_sequence,
        flows=flows,
    )
