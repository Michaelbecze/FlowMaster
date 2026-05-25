import asyncio
import logging

import uvicorn

import config
from storage.database import Database
from api.routes import create_app, manager
from collector.listener import start as start_listener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger("flowmaster")


async def _periodic_push(interval: float = 5.0):
    while True:
        await asyncio.sleep(interval)
        await manager.broadcast_stats()


async def _cleanup(db: Database, interval: float = 3600.0):
    while True:
        await asyncio.sleep(interval)
        await db.cleanup_old(config.FLOW_RETENTION_HOURS)
        logger.info("Old flows cleaned up (retention: %dh)", config.FLOW_RETENTION_HOURS)


async def main():
    db = Database(config.DATABASE_PATH)
    await db.connect()

    app = create_app(db)

    transport = await start_listener(config.NETFLOW_HOST, config.NETFLOW_PORT, db, manager)

    server = uvicorn.Server(uvicorn.Config(
        app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_level="warning",
    ))

    logger.info("Dashboard → http://%s:%d", config.WEB_HOST, config.WEB_PORT)
    logger.info("NetFlow collector → udp://%s:%d", config.NETFLOW_HOST, config.NETFLOW_PORT)

    try:
        await asyncio.gather(
            server.serve(),
            _periodic_push(),
            _cleanup(db),
        )
    finally:
        transport.close()
        await db.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
