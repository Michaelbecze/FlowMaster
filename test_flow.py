"""
Send a synthetic NetFlow v5 packet to localhost:2055 to verify the pipeline.
Run with: python test_flow.py
"""
import socket
import struct
import time

HOST = "127.0.0.1"
PORT = 2055

def make_packet():
    now = int(time.time())
    # Header: version=5, count=3, uptime, unix_secs, unix_nsecs, seq, eng_type, eng_id, sampling
    header = struct.pack("!HHIIIIBBH", 5, 3, 60000, now, 0, 1, 0, 0, 0)

    def record(src, dst, sport, dport, proto, pkts, octets):
        src_b = socket.inet_aton(src)
        dst_b = socket.inet_aton(dst)
        nxt_b = socket.inet_aton("0.0.0.0")
        src_int = struct.unpack("!I", src_b)[0]
        dst_int = struct.unpack("!I", dst_b)[0]
        nxt_int = struct.unpack("!I", nxt_b)[0]
        first = 59000
        last  = 59900
        # format matches RECORD_FMT in netflow_v5.py
        return struct.pack("!IIIHHIIIIHHxBBBHHBBxx",
            src_int, dst_int, nxt_int,
            1, 2,           # input/output interface
            pkts, octets,   # packets, bytes
            first, last,    # first/last uptime ms
            sport, dport,
            0x18,           # tcp_flags (ACK+PSH)
            proto,          # protocol
            0,              # tos
            0, 0,           # src_as, dst_as
            24, 0,          # src_mask, dst_mask
        )

    flows = (
        record("192.168.0.30", "8.8.8.8",     54321, 443,  6,  42, 55296),   # TCP
        record("192.168.0.31", "1.1.1.1",     60001, 53,   17, 10,  640),    # UDP/DNS
        record("192.168.0.30", "192.168.0.31",    0,  0,   1,   5,  420),    # ICMP
    )

    return header + b"".join(flows)

pkt = make_packet()
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(pkt, (HOST, PORT))
sock.close()
print(f"Sent 3 test flows to {HOST}:{PORT}")
print("Wait a moment, then refresh the FlowMaster dashboard.")
