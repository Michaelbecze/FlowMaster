# FlowMaster

A lightweight NetFlow v5 collector and real-time analytics dashboard for home and small-office networks. Receives flows from Cisco IOS switches and pfSense, stores them in SQLite, and serves a live browser-based dashboard with interactive charts.

![Dashboard](https://img.shields.io/badge/dashboard-browser--based-00d4ff?style=flat-square)
![NetFlow](https://img.shields.io/badge/NetFlow-v5-8b5cf6?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-10b981?style=flat-square)

---

## Features

- **NetFlow v5 collector** — asyncio UDP listener on port 2055
- **Real-time dashboard** — WebSocket-pushed stat updates every 5 seconds, full chart refresh every 15 seconds
- **Traffic Volume** — clickable time-series chart; click any point to drill down into the individual flows for that window
- **Protocol Distribution** — doughnut chart breaking down traffic by IP protocol (TCP, UDP, ICMP, etc.)
- **Application Detection** — doughnut chart mapping well-known ports to application names (HTTP, HTTPS, DNS, SSH, RDP, and more)
- **Top Talkers** — horizontal bar chart of the highest-bandwidth source IPs
- **Flow Map** — D3 Sankey diagram showing the top source → destination traffic paths
- **Global time range selector** — switch between 1H, 3H, 6H, 12H, and 24H views; all charts update instantly
- **24-hour retention** — flows older than 24 hours are automatically purged

---

## Requirements

- Python 3.10+
- pip

```
fastapi
uvicorn[standard]
aiosqlite
```

---

## Installation

```bash
git clone https://github.com/Michaelbecze/FlowMaster.git
cd FlowMaster
pip install -r requirements.txt
```

---

## Running

```bash
python main.py
```

Then open **http://\<server-ip\>:8080** in your browser.

By default the app listens on:
| Service | Protocol | Port |
|---|---|---|
| Web dashboard | TCP | 8080 |
| NetFlow collector | UDP | 2055 |

Both hosts and ports can be changed in `config.py`.

---

## Project Structure

```
FlowMaster/
├── main.py                  # Entry point — starts collector + web server
├── config.py                # Ports, paths, retention settings
├── requirements.txt
├── collector/
│   ├── netflow_v5.py        # NetFlow v5 binary packet parser
│   └── listener.py          # asyncio UDP server
├── storage/
│   └── database.py          # aiosqlite / SQLite storage & queries
├── api/
│   └── routes.py            # FastAPI REST endpoints + WebSocket
└── frontend/
    └── index.html           # Single-file dashboard (Chart.js + D3 Sankey)
```

---

## Configuration

Edit `config.py` to change defaults:

```python
NETFLOW_HOST = "0.0.0.0"     # interface to listen on
NETFLOW_PORT = 2055           # UDP port for NetFlow
WEB_HOST     = "0.0.0.0"     # interface for the web server
WEB_PORT     = 8080           # TCP port for the dashboard
DATABASE_PATH = "flowmaster.db"
FLOW_RETENTION_HOURS = 24
```

---

## Application Detection

FlowMaster maps well-known destination/source ports to application names:

| Port(s) | Application |
|---|---|
| 80, 8080, 8000 | HTTP |
| 443, 8443 | HTTPS |
| 53 | DNS |
| 22 | SSH |
| 25, 587, 465 | SMTP |
| 143, 993 | IMAP |
| 3389 | RDP |
| 1194 | OpenVPN |
| 51820 | WireGuard |
| 137–139, 445 | SMB |
| *(others)* | Other |

The full mapping is in `storage/database.py` (`get_applications`) and is easy to extend.

---

## Testing without a real NetFlow source

A test script is included that sends a synthetic 3-flow NetFlow v5 packet to localhost:

```bash
python test_flow.py
```

---

## License

MIT
