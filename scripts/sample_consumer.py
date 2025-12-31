#!/usr/bin/env python3
"""Sample event consumer for demonstrating event consumption.

This script consumes payment events from Kafka/Redpanda topics
and logs them for demonstration purposes.
"""
import asyncio
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from payment_service.config import settings
from payment_service.logging import configure_logging


logger = structlog.get_logger()


TOPICS = [
    "payments.paymentauthorized",
    "payments.paymentdeclined",
    "payments.dlq",
]


async def process_event(topic: str, event: dict) -> None:
    """Process a received event.

    In a real application, this would trigger business logic such as:
    - Sending notifications
    - Updating read models
    - Triggering downstream workflows
    """
    event_type = event.get("event_type", "unknown")
    payload = event.get("payload", {})

    if topic == "payments.dlq":
        logger.warning(
            "dead_letter_event_received",
            event_id=event.get("event_id"),
            event_type=event_type,
            aggregate_id=event.get("aggregate_id"),
            retry_count=event.get("retry_count"),
            error=event.get("error"),
        )
        return

    if event_type == "PaymentAuthorized":
        logger.info(
            "payment_authorized_event",
            event_id=event.get("event_id"),
            payment_id=payload.get("payment_id"),
            payer=payload.get("payer_account_id"),
            payee=payload.get("payee_account_id"),
            amount_cents=payload.get("amount_cents"),
            currency=payload.get("currency"),
        )
    elif event_type == "PaymentDeclined":
        logger.info(
            "payment_declined_event",
            event_id=event.get("event_id"),
            payment_id=payload.get("payment_id"),
            payer=payload.get("payer_account_id"),
            error_code=payload.get("error_code"),
        )
    else:
        logger.info(
            "unknown_event_received",
            event_id=event.get("event_id"),
            event_type=event_type,
        )


async def consume_events() -> None:
    """Main consumer loop."""
    consumer = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers=settings.redpanda_brokers,
        group_id="sample-notification-service",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("shutdown_signal_received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await consumer.start()
        logger.info(
            "consumer_started",
            topics=TOPICS,
            group_id="sample-notification-service",
            brokers=settings.redpanda_brokers,
        )

        while not shutdown_event.is_set():
            try:
                result = await asyncio.wait_for(
                    consumer.getmany(timeout_ms=1000, max_records=100),
                    timeout=2.0,
                )
                for topic_partition, messages in result.items():
                    for msg in messages:
                        await process_event(topic_partition.topic, msg.value)
            except asyncio.TimeoutError:
                continue
            except KafkaError as e:
                logger.error("kafka_error", error=str(e))
                await asyncio.sleep(1)

    finally:
        await consumer.stop()
        logger.info("consumer_stopped")


async def main() -> None:
    """Main entrypoint."""
    configure_logging()
    logger.info("sample_consumer_starting")
    await consume_events()


if __name__ == "__main__":
    asyncio.run(main())
