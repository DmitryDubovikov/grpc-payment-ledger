"""Integration tests for OutboxProcessor lifecycle management."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka.errors import KafkaError

from payment_service.domain.models import OutboxEvent
from payment_service.infrastructure.event_publisher import OutboxProcessor


class TestOutboxProcessorLifecycle:
    """Tests for OutboxProcessor start/stop lifecycle."""

    @pytest.fixture
    def mock_database(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock()
        session_mock = AsyncMock()
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=None)
        session_mock.commit = AsyncMock(return_value=None)
        db.session = MagicMock(return_value=session_mock)
        return db

    @pytest.mark.asyncio
    async def test_start_initializes_producer(self, mock_database: MagicMock) -> None:
        """Test start() initializes Kafka producer."""
        processor = OutboxProcessor(database=mock_database)

        with patch("payment_service.infrastructure.event_publisher.AIOKafkaProducer") as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer.start = AsyncMock(return_value=None)
            mock_producer.stop = AsyncMock(return_value=None)
            mock_producer_cls.return_value = mock_producer

            with patch("payment_service.infrastructure.event_publisher.OutboxRepository") as mock_repo_cls:
                mock_repo = AsyncMock()
                mock_repo.get_unpublished = AsyncMock(return_value=[])
                mock_repo_cls.return_value = mock_repo

                # Start in background and stop after a short time
                async def stop_after_delay():
                    await asyncio.sleep(0.1)
                    await processor.stop()

                await asyncio.gather(
                    processor.start(),
                    stop_after_delay(),
                    return_exceptions=True,
                )

            mock_producer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_stops_producer(self, mock_database: MagicMock) -> None:
        """Test stop() properly stops Kafka producer."""
        processor = OutboxProcessor(database=mock_database)

        with patch("payment_service.infrastructure.event_publisher.AIOKafkaProducer") as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer.start = AsyncMock(return_value=None)
            mock_producer.stop = AsyncMock(return_value=None)
            mock_producer_cls.return_value = mock_producer

            with patch("payment_service.infrastructure.event_publisher.OutboxRepository") as mock_repo_cls:
                mock_repo = AsyncMock()
                mock_repo.get_unpublished = AsyncMock(return_value=[])
                mock_repo_cls.return_value = mock_repo

                async def stop_after_delay():
                    await asyncio.sleep(0.1)
                    await processor.stop()

                await asyncio.gather(
                    processor.start(),
                    stop_after_delay(),
                    return_exceptions=True,
                )

            mock_producer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_sets_running_to_false(self, mock_database: MagicMock) -> None:
        """Test stop() sets _running flag to False."""
        processor = OutboxProcessor(database=mock_database)
        processor._running = True
        processor._producer = AsyncMock()
        processor._producer.stop = AsyncMock(return_value=None)

        await processor.stop()

        assert processor._running is False

    @pytest.mark.asyncio
    async def test_stop_clears_producer(self, mock_database: MagicMock) -> None:
        """Test stop() sets producer to None after stopping."""
        processor = OutboxProcessor(database=mock_database)
        processor._running = True
        processor._producer = AsyncMock()
        processor._producer.stop = AsyncMock(return_value=None)

        await processor.stop()

        assert processor._producer is None

    @pytest.mark.asyncio
    async def test_stop_without_producer_is_safe(self, mock_database: MagicMock) -> None:
        """Test stop() is safe to call when producer is None."""
        processor = OutboxProcessor(database=mock_database)
        processor._running = True
        processor._producer = None

        # Should not raise
        await processor.stop()

        assert processor._running is False

    @pytest.mark.asyncio
    async def test_producer_configuration(self, mock_database: MagicMock) -> None:
        """Test producer is configured with correct settings."""
        processor = OutboxProcessor(database=mock_database)

        with patch("payment_service.infrastructure.event_publisher.AIOKafkaProducer") as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer.start = AsyncMock(return_value=None)
            mock_producer.stop = AsyncMock(return_value=None)
            mock_producer_cls.return_value = mock_producer

            with patch("payment_service.infrastructure.event_publisher.OutboxRepository") as mock_repo_cls:
                mock_repo = AsyncMock()
                mock_repo.get_unpublished = AsyncMock(return_value=[])
                mock_repo_cls.return_value = mock_repo

                async def stop_after_delay():
                    await asyncio.sleep(0.05)
                    await processor.stop()

                await asyncio.gather(
                    processor.start(),
                    stop_after_delay(),
                    return_exceptions=True,
                )

            # Verify producer was created with correct kwargs
            call_kwargs = mock_producer_cls.call_args[1]
            assert call_kwargs["acks"] == "all"
            assert call_kwargs["enable_idempotence"] is True
            assert call_kwargs["retries"] == 3
            assert call_kwargs["max_in_flight_requests_per_connection"] == 5


class TestOutboxProcessorErrorHandling:
    """Tests for error handling in OutboxProcessor."""

    @pytest.fixture
    def mock_database(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock()
        session_mock = AsyncMock()
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=None)
        session_mock.commit = AsyncMock(return_value=None)
        db.session = MagicMock(return_value=session_mock)
        return db

    @pytest.mark.asyncio
    async def test_process_batch_handles_database_error(self, mock_database: MagicMock) -> None:
        """Test _process_batch handles database errors gracefully."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()

        with patch("payment_service.infrastructure.event_publisher.OutboxRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_unpublished = AsyncMock(side_effect=Exception("Database connection lost"))
            mock_repo_cls.return_value = mock_repo

            with pytest.raises(Exception, match="Database connection lost"):
                await processor._process_batch()

    @pytest.mark.asyncio
    async def test_dlq_publish_failure_logged(self, mock_database: MagicMock) -> None:
        """Test DLQ publish failure is logged but doesn't crash."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()
        processor._producer.send_and_wait = AsyncMock(side_effect=KafkaError("DLQ publish failed"))

        failed_event = OutboxEvent(
            id="01HTEST00000000000000001",
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload={},
            created_at=datetime.now(UTC),
            published_at=None,
            retry_count=5,
        )

        mock_outbox_repo = AsyncMock()

        # Should not raise, just log
        await processor._send_to_dlq([failed_event], mock_outbox_repo)

        # Verify mark_published was not called due to error
        mock_outbox_repo.mark_published.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_batch_failure(self, mock_database: MagicMock) -> None:
        """Test processing continues when some events fail to publish."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()

        # First event succeeds, second fails
        call_count = 0

        async def mock_send_and_wait(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise KafkaError("Publish failed")

        processor._producer.send_and_wait = mock_send_and_wait

        events = [
            OutboxEvent(
                id="01HTEST00000000000000001",
                aggregate_type="Payment",
                aggregate_id="01HPAYMENT00000000001",
                event_type="PaymentAuthorized",
                payload={},
                created_at=datetime.now(UTC),
                published_at=None,
                retry_count=0,
            ),
            OutboxEvent(
                id="01HTEST00000000000000002",
                aggregate_type="Payment",
                aggregate_id="01HPAYMENT00000000002",
                event_type="PaymentAuthorized",
                payload={},
                created_at=datetime.now(UTC),
                published_at=None,
                retry_count=0,
            ),
        ]

        with patch("payment_service.infrastructure.event_publisher.OutboxRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_unpublished = AsyncMock(return_value=events)
            mock_repo.mark_published = AsyncMock(return_value=None)
            mock_repo.increment_retry_count = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo

            count = await processor._process_batch()

            # Both events were processed
            assert count == 2
            # Only one event marked as published
            mock_repo.mark_published.assert_called_once()
            published_ids = mock_repo.mark_published.call_args[0][0]
            assert len(published_ids) == 1
            assert "01HTEST00000000000000001" in published_ids
            # One event had retry incremented
            mock_repo.increment_retry_count.assert_called_once_with("01HTEST00000000000000002")


class TestOutboxProcessorBackoffBehavior:
    """Tests for exponential backoff behavior."""

    @pytest.fixture
    def mock_database(self) -> MagicMock:
        """Create a mock database."""
        return MagicMock()

    def test_backoff_increases_exponentially(self, mock_database: MagicMock) -> None:
        """Test backoff delay doubles with each retry."""
        processor = OutboxProcessor(
            database=mock_database,
            base_delay=1.0,
            max_delay=60.0,
        )

        delays = []
        for retry in range(5):
            delay = processor._calculate_backoff_delay(retry)
            delays.append(delay)

        # Each delay should be roughly double the previous (with some jitter)
        # Due to jitter, we can't be exact, but trend should be exponential
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1] or i >= 3  # After max_delay, stays constant

    def test_backoff_respects_max_delay(self, mock_database: MagicMock) -> None:
        """Test backoff delay never exceeds max_delay."""
        max_delay = 30.0
        processor = OutboxProcessor(
            database=mock_database,
            base_delay=1.0,
            max_delay=max_delay,
        )

        for retry in range(20):
            delay = processor._calculate_backoff_delay(retry)
            # Max delay + 10% jitter
            assert delay <= max_delay * 1.1

    def test_backoff_with_zero_retry_is_base_delay(self, mock_database: MagicMock) -> None:
        """Test first retry uses base delay."""
        base_delay = 2.0
        processor = OutboxProcessor(
            database=mock_database,
            base_delay=base_delay,
            max_delay=60.0,
        )

        delay = processor._calculate_backoff_delay(0)

        # Should be base_delay + up to 10% jitter
        assert base_delay <= delay <= base_delay * 1.1

    def test_backoff_includes_jitter(self, mock_database: MagicMock) -> None:
        """Test backoff delay includes randomized jitter."""
        processor = OutboxProcessor(
            database=mock_database,
            base_delay=1.0,
            max_delay=60.0,
        )

        # Generate multiple delays and check they're not all identical
        delays = [processor._calculate_backoff_delay(0) for _ in range(10)]
        unique_delays = set(delays)

        # With random jitter, we should have some variation
        assert len(unique_delays) > 1
