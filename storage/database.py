import time
import logging
import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS flows (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    REAL    NOT NULL,
    src_ip       TEXT    NOT NULL,
    dst_ip       TEXT    NOT NULL,
    src_port     INTEGER NOT NULL,
    dst_port     INTEGER NOT NULL,
    protocol     INTEGER NOT NULL,
    bytes        INTEGER NOT NULL,
    packets      INTEGER NOT NULL,
    duration_ms  INTEGER NOT NULL,
    exporter_ip  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ts ON flows(timestamp);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("Database ready: %s", self.path)

    async def close(self):
        if self._db:
            await self._db.close()

    async def insert_flows(self, flows, timestamp: float, exporter_ip: str):
        rows = [
            (timestamp, f.src_ip, f.dst_ip, f.src_port, f.dst_port,
             f.protocol, f.bytes, f.packets, f.duration_ms, exporter_ip)
            for f in flows
        ]
        await self._db.executemany(
            "INSERT INTO flows VALUES (NULL,?,?,?,?,?,?,?,?,?,?)", rows
        )
        await self._db.commit()

    async def get_stats(self, hours: float = 1.0):
        since = time.time() - hours * 3600
        async with self._db.execute(
            """SELECT COUNT(*)           AS total_flows,
                      COALESCE(SUM(bytes),0) AS total_bytes,
                      COUNT(DISTINCT src_ip) AS unique_sources,
                      COUNT(DISTINCT dst_ip) AS unique_destinations
               FROM flows WHERE timestamp > ?""",
            (since,),
        ) as cur:
            return dict(await cur.fetchone())

    async def get_traffic_over_time(self, hours: float = 1.0, buckets: int = 60):
        since    = time.time() - hours * 3600
        interval = (hours * 3600) / buckets          # seconds per bucket
        async with self._db.execute(
            """SELECT CAST(timestamp / ? AS INTEGER) * ? AS bucket_ts,
                      SUM(bytes) AS total_bytes,
                      COUNT(*)   AS flow_count
               FROM flows WHERE timestamp > ?
               GROUP BY bucket_ts ORDER BY bucket_ts""",
            (interval, interval, since),
        ) as cur:
            rows = await cur.fetchall()
        import datetime
        result = []
        for row in rows:
            d = dict(row)
            d["bucket"] = datetime.datetime.utcfromtimestamp(d.pop("bucket_ts")).strftime("%Y-%m-%dT%H:%M:%S")
            result.append(d)
        return result

    async def get_top_talkers(self, limit: int = 10, hours: float = 1.0):
        since = time.time() - hours * 3600
        async with self._db.execute(
            """SELECT src_ip, SUM(bytes) AS total_bytes, COUNT(*) AS flow_count
               FROM flows WHERE timestamp > ?
               GROUP BY src_ip ORDER BY total_bytes DESC LIMIT ?""",
            (since, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_top_destinations(self, limit: int = 10, hours: float = 1.0):
        since = time.time() - hours * 3600
        async with self._db.execute(
            """SELECT dst_ip, SUM(bytes) AS total_bytes, COUNT(*) AS flow_count
               FROM flows WHERE timestamp > ?
               GROUP BY dst_ip ORDER BY total_bytes DESC LIMIT ?""",
            (since, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_protocols(self, hours: float = 1.0):
        since = time.time() - hours * 3600
        async with self._db.execute(
            """SELECT protocol, SUM(bytes) AS total_bytes, COUNT(*) AS flow_count
               FROM flows WHERE timestamp > ?
               GROUP BY protocol ORDER BY total_bytes DESC""",
            (since,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_recent_flows(self, limit: int = 50):
        async with self._db.execute(
            "SELECT * FROM flows ORDER BY timestamp DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_applications(self, hours: float = 1.0, limit: int = 10):
        _PORT_APPS = {
            80: 'HTTP',   8080: 'HTTP',   8000: 'HTTP',   8008: 'HTTP',
            443: 'HTTPS', 8443: 'HTTPS',
            53: 'DNS',
            22: 'SSH',
            25: 'SMTP',   587: 'SMTP',    465: 'SMTP',
            143: 'IMAP',  993: 'IMAP',
            110: 'POP3',  995: 'POP3',
            20: 'FTP',    21: 'FTP',
            3389: 'RDP',
            5060: 'SIP',  5061: 'SIP',
            123: 'NTP',
            179: 'BGP',
            161: 'SNMP',  162: 'SNMP',
            67: 'DHCP',   68: 'DHCP',
            1194: 'OpenVPN',
            51820: 'WireGuard',
            500: 'IKE/IPsec', 4500: 'IKE/IPsec',
            1723: 'PPTP',
            389: 'LDAP',  636: 'LDAPS',
            137: 'SMB',   138: 'SMB',    139: 'SMB',    445: 'SMB',
            3306: 'MySQL', 5432: 'PostgreSQL',
        }
        since = time.time() - hours * 3600
        async with self._db.execute(
            """SELECT protocol, src_port, dst_port, SUM(bytes) AS total_bytes
               FROM flows WHERE timestamp > ?
               GROUP BY protocol, src_port, dst_port""",
            (since,),
        ) as cur:
            rows = await cur.fetchall()
        app_bytes: dict[str, int] = {}
        for row in rows:
            prot, sp, dp, b = row["protocol"], row["src_port"], row["dst_port"], row["total_bytes"]
            if prot == 1:
                app = "ICMP"
            else:
                app = _PORT_APPS.get(dp) or _PORT_APPS.get(sp) or "Other"
            app_bytes[app] = app_bytes.get(app, 0) + b
        result = sorted(
            [{"app": k, "total_bytes": v} for k, v in app_bytes.items()],
            key=lambda x: x["total_bytes"], reverse=True,
        )
        return result[:limit]

    async def get_flows_in_range(self, from_ts: float, to_ts: float, limit: int = 100):
        async with self._db.execute(
            """SELECT * FROM flows WHERE timestamp >= ? AND timestamp < ?
               ORDER BY bytes DESC LIMIT ?""",
            (from_ts, to_ts, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_sankey_data(self, limit: int = 30, hours: float = 1.0):
        since = time.time() - hours * 3600
        async with self._db.execute(
            """SELECT src_ip, dst_ip, SUM(bytes) AS total_bytes
               FROM flows WHERE timestamp > ?
               GROUP BY src_ip, dst_ip
               ORDER BY total_bytes DESC LIMIT ?""",
            (since, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def cleanup_old(self, hours: float = 24.0):
        cutoff = time.time() - hours * 3600
        await self._db.execute("DELETE FROM flows WHERE timestamp < ?", (cutoff,))
        await self._db.commit()
