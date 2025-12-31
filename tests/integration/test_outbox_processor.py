"""Integration tests for OutboxProcessor and event publishing."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka.errors import KafkaError

from payment_service.domain.models import OutboxEvent
from payment_service.infrastructure.event_publisher import OutboxProcessor


class TestOutboxProcessor:
    """Tests for OutboxProcessor functionality."""

    @pytest.fixture
    def mock_database(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock()
        session_mock = AsyncMock()
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=None)
        db.session = MagicMock(return_value=session_mock)
        return db

    @pytest.fixture
    def sample_outbox_events(self) -> list[OutboxEvent]:
        """Create sample outbox events for testing."""
        return [
            OutboxEvent(
                id="01HTEST00000000000000001",
                aggregate_type="Payment",
                aggregate_id="01HPAYMENT00000000001",
                event_type="PaymentAuthorized",
                payload={
                    "payment_id": "01HPAYMENT00000000001",
                    "payer_account_id": "01HPAYER0000000000001",
                    "payee_account_id": "01HPAYEE0000000000001",
                    "amount_cents": 1000,
                    "currency": "USD",
                },
                created_at=datetime.now(UTC),
                published_at=None,
                retry_count=0,
            ),
            OutboxEvent(
                id="01HTEST00000000000000002",
                aggregate_type="Payment",
                aggregate_id="01HPAYMENT00000000002",
                event_type="PaymentAuthorized",
                payload={
                    "payment_id": "01HPAYMENT00000000002",
                    "payer_account_id": "01HPAYER0000000000002",
                    "payee_account_id": "01HPAYEE0000000000002",
                    "amount_cents": 2000,
                    "currency": "USD",
                },
                created_at=datetime.now(UTC),
                published_at=None,
                retry_count=0,
            ),
        ]

    @pytest.fixture
    def failed_outbox_event(self) -> OutboxEvent:
        """Create an event that has exceeded max retries."""
        return OutboxEvent(
            id="01HTEST00000000000000003",
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000003",
            event_type="PaymentAuthorized",
            payload={
                "payment_id": "01HPAYMENT00000000003",
                "payer_account_id": "01HPAYER0000000000003",
                "payee_account_id": "01HPAYEE0000000000003",
                "amount_cents": 3000,
                "currency": "USD",
            },
            created_at=datetime.now(UTC),
            published_at=None,
            retry_count=5,
        )

    def test_outbox_processor_initialization(self, mock_database: MagicMock) -> None:
        """Test OutboxProcessor initializes with correct defaults."""
        processor = OutboxProcessor(database=mock_database)

        assert processor._batch_size == 100
        assert processor._poll_interval == 1.0
        assert processor._max_retries == 5
        assert processor._running is False

    def test_outbox_processor_custom_config(self, mock_database: MagicMock) -> None:
        """Test OutboxProcessor with custom configuration."""
        processor = OutboxProcessor(
            database=mock_database,
            batch_size=50,
            poll_interval=2.0,
            max_retries=3,
            base_delay=2.0,
            max_delay=120.0,
        )

        assert processor._batch_size == 50
        assert processor._poll_interval == 2.0
        assert processor._max_retries == 3
        assert processor._base_delay == 2.0
        assert processor._max_delay == 120.0

    def test_calculate_backoff_delay(self, mock_database: MagicMock) -> None:
        """Test exponential backoff calculation."""
        processor = OutboxProcessor(database=mock_database, base_delay=1.0, max_delay=60.0)

        delay_0 = processor._calculate_backoff_delay(0)
        delay_1 = processor._calculate_backoff_delay(1)
        delay_2 = processor._calculate_backoff_delay(2)
        delay_10 = processor._calculate_backoff_delay(10)

        assert 1.0 <= delay_0 <= 1.1
        assert 2.0 <= delay_1 <= 2.2
        assert 4.0 <= delay_2 <= 4.4
        assert delay_10 <= 66.0

    @pytest.mark.asyncio
    async def test_publish_event_success(
        self,
        mock_database: MagicMock,
        sample_outbox_events: list[OutboxEvent],
    ) -> None:
        """Test successful event publishing."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()
        processor._producer.send_and_wait = AsyncMock(return_value=None)

        event = sample_outbox_events[0]
        result = await processor._publish_event(event)

        assert result is True
        processor._producer.send_and_wait.assert_called_once()
        call_kwargs = processor._producer.send_and_wait.call_args
        assert call_kwargs.kwargs["topic"] == "payments.paymentauthorized"
        assert call_kwargs.kwargs["key"] == event.aggregate_id

    @pytest.mark.asyncio
    async def test_publish_event_failure(
        self,
        mock_database: MagicMock,
        sample_outbox_events: list[OutboxEvent],
    ) -> None:
        """Test event publishing failure handling."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()
        processor._producer.send_and_wait = AsyncMock(side_effect=KafkaError("Connection failed"))

        event = sample_outbox_events[0]
        result = await processor._publish_event(event)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_event_no_producer(
        self,
        mock_database: MagicMock,
        sample_outbox_events: list[OutboxEvent],
    ) -> None:
        """Test publishing without producer returns False."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = None

        event = sample_outbox_events[0]
        result = await processor._publish_event(event)

        assert result is False

    @pytest.mark.asyncio
    async def test_process_batch_empty(self, mock_database: MagicMock) -> None:
        """Test processing empty batch."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()

        with patch("payment_service.infrastructure.event_publisher.OutboxRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_unpublished = AsyncMock(return_value=[])
            mock_repo_cls.return_value = mock_repo

            count = await processor._process_batch()

            assert count == 0

    @pytest.mark.asyncio
    async def test_process_batch_with_events(
        self,
        mock_database: MagicMock,
        sample_outbox_events: list[OutboxEvent],
    ) -> None:
        """Test processing batch with events."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()
        processor._producer.send_and_wait = AsyncMock(return_value=None)

        with patch("payment_service.infrastructure.event_publisher.OutboxRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_unpublished = AsyncMock(return_value=sample_outbox_events)
            mock_repo.mark_published = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo

            count = await processor._process_batch()

            assert count == 2
            mock_repo.mark_published.assert_called_once()
            call_args = mock_repo.mark_published.call_args[0][0]
            assert len(call_args) == 2

    @pytest.mark.asyncio
    async def test_send_to_dlq(
        self,
        mock_database: MagicMock,
        failed_outbox_event: OutboxEvent,
    ) -> None:
        """Test sending event to dead letter queue."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()
        processor._producer.send_and_wait = AsyncMock(return_value=None)

        mock_outbox_repo = AsyncMock()
        mock_outbox_repo.mark_published = AsyncMock(return_value=None)

        await processor._send_to_dlq([failed_outbox_event], mock_outbox_repo)

        processor._producer.send_and_wait.assert_called_once()
        call_kwargs = processor._producer.send_and_wait.call_args
        assert call_kwargs.kwargs["topic"] == "payments.dlq"
        assert "retry_count" in call_kwargs.kwargs["value"]
        assert "failed_at" in call_kwargs.kwargs["value"]
        assert "error" in call_kwargs.kwargs["value"]
        mock_outbox_repo.mark_published.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_retry(
        self,
        mock_database: MagicMock,
        sample_outbox_events: list[OutboxEvent],
    ) -> None:
        """Test retry handling increments retry count."""
        processor = OutboxProcessor(database=mock_database)

        mock_outbox_repo = AsyncMock()
        mock_outbox_repo.increment_retry_count = AsyncMock(return_value=None)

        event = sample_outbox_events[0]
        await processor._handle_retry(event, mock_outbox_repo)

        mock_outbox_repo.increment_retry_count.assert_called_once_with(event.id)


class TestOutboxProcessorEventFormat:
    """Tests for event format and structure."""

    @pytest.fixture
    def mock_database(self) -> MagicMock:
        """Create a mock database."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_event_format_matches_schema(self, mock_database: MagicMock) -> None:
        """Test published event matches expected JSON schema format."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()

        captured_value = None

        async def capture_send(topic: str, key: str, value: dict) -> None:
            nonlocal captured_value
            captured_value = value

        processor._producer.send_and_wait = capture_send

        event = OutboxEvent(
            id="01HTEST00000000000000001",
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload={
                "payment_id": "01HPAYMENT00000000001",
                "payer_account_id": "01HPAYER0000000000001",
                "payee_account_id": "01HPAYEE0000000000001",
                "amount_cents": 1000,
                "currency": "USD",
            },
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            published_at=None,
            retry_count=0,
        )

        await processor._publish_event(event)

        assert captured_value is not None
        assert captured_value["event_id"] == event.id
        assert captured_value["aggregate_type"] == "Payment"
        assert captured_value["aggregate_id"] == event.aggregate_id
        assert captured_value["event_type"] == "PaymentAuthorized"
        assert captured_value["payload"] == event.payload
        assert "timestamp" in captured_value

    @pytest.mark.asyncio
    async def test_topic_naming_convention(self, mock_database: MagicMock) -> None:
        """Test topic names follow expected convention."""
        processor = OutboxProcessor(database=mock_database)
        processor._producer = AsyncMock()

        captured_topic = None

        async def capture_send(topic: str, key: str, value: dict) -> None:
            nonlocal captured_topic
            captured_topic = topic

        processor._producer.send_and_wait = capture_send

        event = OutboxEvent(
            id="01HTEST00000000000000001",
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload={},
            created_at=datetime.now(UTC),
            published_at=None,
            retry_count=0,
        )

        await processor._publish_event(event)

        assert captured_topic == "payments.paymentauthorized"
