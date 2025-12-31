"""Unit tests for OutboxEvent domain model."""

from datetime import UTC, datetime

from payment_service.domain.models import OutboxEvent


class TestOutboxEvent:
    """Tests for OutboxEvent domain model."""

    def test_outbox_event_creation(self) -> None:
        """Test OutboxEvent can be created with required fields."""
        event = OutboxEvent(
            id="01HTEST00000000000000001",
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload={"payment_id": "01HPAYMENT00000000001", "amount_cents": 1000},
        )

        assert event.id == "01HTEST00000000000000001"
        assert event.aggregate_type == "Payment"
        assert event.aggregate_id == "01HPAYMENT00000000001"
        assert event.event_type == "PaymentAuthorized"
        assert event.payload == {"payment_id": "01HPAYMENT00000000001", "amount_cents": 1000}
        assert event.published_at is None
        assert event.retry_count == 0

    def test_outbox_event_create_factory(self) -> None:
        """Test OutboxEvent.create factory method generates ULID."""
        event = OutboxEvent.create(
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload={"payment_id": "01HPAYMENT00000000001"},
        )

        assert len(event.id) == 26  # ULID length
        assert event.aggregate_type == "Payment"
        assert event.event_type == "PaymentAuthorized"
        assert event.published_at is None
        assert event.retry_count == 0

    def test_outbox_event_with_custom_timestamp(self) -> None:
        """Test OutboxEvent with custom created_at timestamp."""
        custom_time = datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC)
        event = OutboxEvent(
            id="01HTEST00000000000000001",
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload={},
            created_at=custom_time,
        )

        assert event.created_at == custom_time

    def test_outbox_event_with_published_at(self) -> None:
        """Test OutboxEvent can have published_at set."""
        published_time = datetime(2024, 6, 15, 10, 35, 0, tzinfo=UTC)
        event = OutboxEvent(
            id="01HTEST00000000000000001",
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload={},
            published_at=published_time,
        )

        assert event.published_at == published_time

    def test_outbox_event_with_retry_count(self) -> None:
        """Test OutboxEvent with non-zero retry count."""
        event = OutboxEvent(
            id="01HTEST00000000000000001",
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload={},
            retry_count=3,
        )

        assert event.retry_count == 3

    def test_outbox_event_payload_structure(self) -> None:
        """Test OutboxEvent payload can contain nested structures."""
        complex_payload = {
            "payment_id": "01HPAYMENT00000000001",
            "payer_account_id": "01HPAYER0000000000001",
            "payee_account_id": "01HPAYEE0000000000001",
            "amount_cents": 5000,
            "currency": "USD",
            "metadata": {
                "source": "api",
                "ip_address": "192.168.1.1",
            },
        }

        event = OutboxEvent.create(
            aggregate_type="Payment",
            aggregate_id="01HPAYMENT00000000001",
            event_type="PaymentAuthorized",
            payload=complex_payload,
        )

        assert event.payload == complex_payload
        assert event.payload["metadata"]["source"] == "api"

    def test_outbox_event_different_event_types(self) -> None:
        """Test OutboxEvent supports different event types."""
        event_types = ["PaymentAuthorized", "PaymentDeclined", "PaymentRefunded"]

        for event_type in event_types:
            event = OutboxEvent.create(
                aggregate_type="Payment",
                aggregate_id="01HPAYMENT00000000001",
                event_type=event_type,
                payload={},
            )
            assert event.event_type == event_type

    def test_outbox_event_different_aggregate_types(self) -> None:
        """Test OutboxEvent supports different aggregate types."""
        aggregate_types = ["Payment", "Account", "Transaction"]

        for agg_type in aggregate_types:
            event = OutboxEvent.create(
                aggregate_type=agg_type,
                aggregate_id="01HAGGREGATE000000001",
                event_type="SomeEvent",
                payload={},
            )
            assert event.aggregate_type == agg_type
