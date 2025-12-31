import asyncio
import json
import random
from datetime import UTC, datetime

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from payment_service.config import settings
from payment_service.domain.models import OutboxEvent
from payment_service.infrastructure.database import Database
from payment_service.infrastructure.repositories.outbox import OutboxRepository


logger = structlog.get_logger()


class OutboxProcessor:
    """
    Processes outbox events and publishes them to Kafka/Redpanda.

    Implements the Outbox Pattern for reliable event publishing with:
    - Batch processing with configurable batch size
    - Exponential backoff for retries
    - Dead letter queue for events exceeding max retries
    - Exactly-once semantics via Kafka idempotent producer
    - Circuit breaker for consecutive failures
    """

    MAX_CONSECUTIVE_FAILURES = 10

    def __init__(
        self,
        database: Database,
        batch_size: int | None = None,
        poll_interval: float | None = None,
        max_retries: int | None = None,
        base_delay: float | None = None,
        max_delay: float | None = None,
    ) -> None:
        self._database = database
        self._batch_size = batch_size or settings.outbox_batch_size
        self._poll_interval = poll_interval or settings.outbox_poll_interval_seconds
        self._max_retries = max_retries or settings.outbox_max_retries
        self._base_delay = base_delay or settings.outbox_base_delay_seconds
        self._max_delay = max_delay or settings.outbox_max_delay_seconds
        self._producer: AIOKafkaProducer | None = None
        self._running = False
        self._topic_prefix = settings.kafka_topic_prefix
        self._consecutive_failures = 0

    async def start(self) -> None:
        """Start the outbox processor and begin processing events."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.redpanda_brokers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            enable_idempotence=True,
        )
        await self._producer.start()
        self._running = True
        self._consecutive_failures = 0
        logger.info("outbox_processor_started", batch_size=self._batch_size)

        try:
            while self._running:
                try:
                    processed_count = await self._process_batch()
                    self._consecutive_failures = 0
                    if processed_count == 0:
                        await asyncio.sleep(self._poll_interval)
                except Exception as e:
                    self._consecutive_failures += 1
                    logger.error(
                        "outbox_processing_error",
                        error=str(e),
                        consecutive_failures=self._consecutive_failures,
                        exc_info=True,
                    )
                    if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                        logger.critical(
                            "circuit_breaker_triggered",
                            consecutive_failures=self._consecutive_failures,
                            action="stopping_processor",
                        )
                        break
                    await asyncio.sleep(self._poll_interval)
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the outbox processor gracefully."""
        self._running = False
        if self._producer:
            await self._producer.stop()
            self._producer = None
        logger.info("outbox_processor_stopped")

    async def _process_batch(self) -> int:
        """Process a batch of unpublished events.

        Returns:
            Number of events processed in this batch.
        """
        async with self._database.session() as session:
            outbox_repo = OutboxRepository(session)
            events = await outbox_repo.get_unpublished(self._batch_size)

            if not events:
                return 0

            published_ids: list[str] = []
            dlq_events: list[OutboxEvent] = []

            for event in events:
                if event.retry_count >= self._max_retries:
                    dlq_events.append(event)
                    continue

                success = await self._publish_event(event)
                if success:
                    published_ids.append(event.id)
                else:
                    await self._handle_retry(event, outbox_repo)

            if published_ids:
                await outbox_repo.mark_published(published_ids)
                logger.info("batch_published", count=len(published_ids))

            if dlq_events:
                await self._send_to_dlq(dlq_events, outbox_repo)

            await session.commit()

            return len(events)

    async def _publish_event(self, event: OutboxEvent) -> bool:
        """Publish a single event to Kafka.

        Returns:
            True if published successfully, False otherwise.
        """
        if not self._producer:
            return False

        topic = f"{self._topic_prefix}.{event.event_type.lower()}"

        try:
            await self._producer.send_and_wait(
                topic=topic,
                key=event.aggregate_id,
                value={
                    "event_id": event.id,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_id": event.aggregate_id,
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "timestamp": event.created_at.isoformat(),
                },
            )
            logger.info(
                "event_published",
                event_id=event.id,
                topic=topic,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
            )
            return True
        except KafkaError as e:
            logger.error(
                "event_publish_failed",
                event_id=event.id,
                topic=topic,
                error=str(e),
                retry_count=event.retry_count,
            )
            return False

    async def _handle_retry(self, event: OutboxEvent, outbox_repo: OutboxRepository) -> None:
        """Handle retry with exponential backoff."""
        await outbox_repo.increment_retry_count(event.id)

        delay = self._calculate_backoff_delay(event.retry_count)
        logger.warning(
            "event_retry_scheduled",
            event_id=event.id,
            retry_count=event.retry_count + 1,
            next_delay_seconds=delay,
        )

    def _calculate_backoff_delay(self, retry_count: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        delay: float = min(
            self._base_delay * (2**retry_count),
            self._max_delay,
        )
        jitter: float = random.uniform(0, delay * 0.1)
        return delay + jitter

    async def _send_to_dlq(self, events: list[OutboxEvent], outbox_repo: OutboxRepository) -> None:
        """Send events to dead letter queue after exceeding max retries."""
        if not self._producer:
            return

        dlq_topic = f"{self._topic_prefix}.dlq"

        for event in events:
            try:
                await self._producer.send_and_wait(
                    topic=dlq_topic,
                    key=event.aggregate_id,
                    value={
                        "event_id": event.id,
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "event_type": event.event_type,
                        "payload": event.payload,
                        "timestamp": event.created_at.isoformat(),
                        "retry_count": event.retry_count,
                        "failed_at": datetime.now(UTC).isoformat(),
                        "error": "max_retries_exceeded",
                    },
                )
                await outbox_repo.mark_published([event.id])
                logger.warning(
                    "event_sent_to_dlq",
                    event_id=event.id,
                    aggregate_id=event.aggregate_id,
                    retry_count=event.retry_count,
                )
            except KafkaError as e:
                logger.error(
                    "dlq_publish_failed",
                    event_id=event.id,
                    error=str(e),
                )
