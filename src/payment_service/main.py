import asyncio
import signal
from typing import NoReturn

import structlog

from payment_service.config import settings
from payment_service.grpc_server import GrpcServer
from payment_service.infrastructure.database import Database
from payment_service.logging import configure_logging


logger = structlog.get_logger()


async def main() -> NoReturn:
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
    )

    logger.info(
        "starting_payment_service",
        grpc_port=settings.grpc_port,
        log_level=settings.log_level,
    )

    database = Database(settings.database_url)
    server = GrpcServer(database)

    loop = asyncio.get_running_loop()

    async def shutdown() -> None:
        logger.info("shutting_down")
        await server.stop()
        await database.close()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown()),
        )

    await server.start(port=settings.grpc_port)
    await server.wait_for_termination()

    raise SystemExit(0)


if __name__ == "__main__":
    asyncio.run(main())
