"""Parser tests: one valid packet, one malformed/truncated packet (constitution
Testing Standards; FR-015). Generalized from the existing project's test_flow.py."""

from __future__ import annotations

import socket
import struct
import time

import pytest

from src.netflow_v5 import (
    HEADER_LEN,
    RECORD_LEN,
    MalformedPacketError,
    parse_packet,
)


def _ip_to_int(ip: str) -> int:
    return struct.unpack("!I", socket.inet_aton(ip))[0]


def _make_valid_packet(num_flows: int = 3) -> bytes:
    now = int(time.time())
    header = struct.pack("!HHIIIIBBH", 5, num_flows, 60000, now, 0, 1, 0, 0, 0)

    def record(src: str, dst: str, sport: int, dport: int, proto: int, pkts: int, octets: int) -> bytes:
        return struct.pack(
            "!IIIHHIIIIHHxBBBHHBBxx",
            _ip_to_int(src),
            _ip_to_int(dst),
            _ip_to_int("0.0.0.0"),
            1,
            2,
            pkts,
            octets,
            59000,
            59900,
            sport,
            dport,
            0x18,
            proto,
            0,
            0,
            0,
            24,
            0,
        )

    records = [
        record("192.168.0.30", "8.8.8.8", 54321, 443, 6, 42, 55296),
        record("192.168.0.31", "1.1.1.1", 60001, 53, 17, 10, 640),
        record("192.168.0.30", "192.168.0.31", 0, 0, 5, 1, 420),
    ][:num_flows]
    return header + b"".join(records)


class TestValidPacket:
    def test_parses_header_and_all_flows(self) -> None:
        packet = _make_valid_packet(3)

        parsed = parse_packet(packet)

        assert parsed.version == 5
        assert parsed.count == 3
        assert len(parsed.flows) == 3

    def test_first_flow_fields_round_trip(self) -> None:
        packet = _make_valid_packet(1)

        parsed = parse_packet(packet)

        flow = parsed.flows[0]
        assert flow.src_addr == "192.168.0.30"
        assert flow.dst_addr == "8.8.8.8"
        assert flow.src_port == 54321
        assert flow.dst_port == 443
        assert flow.protocol == 6
        assert flow.application == "HTTPS"
        assert flow.bytes == 55296
        assert flow.packets == 42


class TestMalformedPacket:
    def test_empty_payload_is_rejected(self) -> None:
        with pytest.raises(MalformedPacketError):
            parse_packet(b"")

    def test_truncated_header_is_rejected(self) -> None:
        with pytest.raises(MalformedPacketError):
            parse_packet(b"\x00" * (HEADER_LEN - 1))

    def test_declared_count_exceeding_payload_is_rejected(self) -> None:
        # Header claims 5 flow records but only one full record's worth of bytes follow.
        header = struct.pack("!HHIIIIBBH", 5, 5, 0, 0, 0, 0, 0, 0, 0)
        packet = header + b"\x00" * RECORD_LEN

        with pytest.raises(MalformedPacketError):
            parse_packet(packet)

    def test_unsupported_version_is_rejected(self) -> None:
        header = struct.pack("!HHIIIIBBH", 9, 0, 0, 0, 0, 0, 0, 0, 0)

        with pytest.raises(MalformedPacketError):
            parse_packet(header)

    def test_one_malformed_packet_does_not_affect_the_next(self) -> None:
        """FR-015: a bad packet must not affect processing of others."""
        bad = b"\x00" * 4
        good = _make_valid_packet(1)

        with pytest.raises(MalformedPacketError):
            parse_packet(bad)

        parsed = parse_packet(good)
        assert len(parsed.flows) == 1
