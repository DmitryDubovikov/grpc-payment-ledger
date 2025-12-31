#!/usr/bin/env python3
"""Outbox processor entrypoint script.

Runs the OutboxProcessor as a standalone background worker that polls
the outbox table and publishes events to Kafka/Redpanda.
"""
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import structlog

from payment_service.config import settings
from payment_service.infrastructure.database import Database
from payment_service.infrastructure.event_publisher import OutboxProcessor
from payment_service.logging import configure_logging


logger = structlog.get_logger()


async def main() -> None:
    """Main entrypoint for the outbox processor."""
    configure_logging()

    logger.info(
        "outbox_processor_starting",
        database_url=settings.database_url.split("@")[-1],
        redpanda_brokers=settings.redpanda_brokers,
        batch_size=settings.outbox_batch_size,
        poll_interval=settings.outbox_poll_interval_seconds,
    )

    database = Database(settings.database_url)
    processor = OutboxProcessor(database=database)

    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("shutdown_signal_received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    processor_task = asyncio.create_task(processor.start())

    try:
        await shutdown_event.wait()
    finally:
        logger.info("initiating_graceful_shutdown")
        await processor.stop()
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        await database.close()
        logger.info("outbox_processor_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
