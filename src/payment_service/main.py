import asyncio
import signal
from typing import NoReturn

import structlog

from payment_service.api.metrics_server import MetricsServer
from payment_service.config import settings
from payment_service.grpc_server import GrpcServer
from payment_service.infrastructure.database import Database
from payment_service.infrastructure.redis_client import RedisClient
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
        metrics_port=settings.metrics_port,
        log_level=settings.log_level,
        rate_limit_enabled=settings.rate_limit_enabled,
        metrics_enabled=settings.metrics_enabled,
    )

    database = Database(settings.database_url)

    redis_client: RedisClient | None = None
    if settings.rate_limit_enabled:
        redis_client = RedisClient(settings.redis_url)
        await redis_client.connect()

    metrics_server: MetricsServer | None = None
    if settings.metrics_enabled:
        metrics_server = MetricsServer(
            host=settings.metrics_host,
            port=settings.metrics_port,
        )
        await metrics_server.start()

    server = GrpcServer(
        database=database,
        redis_client=redis_client,
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_max_requests=settings.rate_limit_max_requests,
        rate_limit_window_seconds=settings.rate_limit_window_seconds,
    )

    loop = asyncio.get_running_loop()

    async def shutdown() -> None:
        logger.info("shutting_down")
        await server.stop()
        if metrics_server:
            await metrics_server.stop()
        if redis_client:
            await redis_client.close()
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
