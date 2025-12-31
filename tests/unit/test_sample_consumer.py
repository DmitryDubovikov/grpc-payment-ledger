"""Unit tests for sample consumer event processing."""

# Import the process_event function from sample_consumer
# Note: We need to handle the sys.path manipulation in the script
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestProcessEvent:
    """Tests for process_event function."""

    @pytest.fixture(autouse=True)
    def setup_logger_mock(self):
        """Mock the logger for all tests."""
        with patch("scripts.sample_consumer.logger") as mock_logger:
            self.mock_logger = mock_logger
            yield

    @pytest.mark.asyncio
    async def test_process_payment_authorized_event(self) -> None:
        """Test processing PaymentAuthorized event logs correctly."""
        # Import here to ensure mocking is set up
        from scripts.sample_consumer import process_event

        event = {
            "event_id": "01HTEST00000000000000001",
            "event_type": "PaymentAuthorized",
            "aggregate_id": "01HPAYMENT00000000001",
            "payload": {
                "payment_id": "01HPAYMENT00000000001",
                "payer_account_id": "01HPAYER0000000000001",
                "payee_account_id": "01HPAYEE0000000000001",
                "amount_cents": 1000,
                "currency": "USD",
            },
        }

        await process_event("payments.paymentauthorized", event)

        self.mock_logger.info.assert_called_once()
        call_args = self.mock_logger.info.call_args
        assert call_args[0][0] == "payment_authorized_event"
        assert call_args[1]["payment_id"] == "01HPAYMENT00000000001"
        assert call_args[1]["amount_cents"] == 1000

    @pytest.mark.asyncio
    async def test_process_payment_declined_event(self) -> None:
        """Test processing PaymentDeclined event logs correctly."""
        from scripts.sample_consumer import process_event

        event = {
            "event_id": "01HTEST00000000000000002",
            "event_type": "PaymentDeclined",
            "aggregate_id": "01HPAYMENT00000000002",
            "payload": {
                "payment_id": "01HPAYMENT00000000002",
                "payer_account_id": "01HPAYER0000000000001",
                "error_code": "INSUFFICIENT_FUNDS",
            },
        }

        await process_event("payments.paymentdeclined", event)

        self.mock_logger.info.assert_called_once()
        call_args = self.mock_logger.info.call_args
        assert call_args[0][0] == "payment_declined_event"
        assert call_args[1]["error_code"] == "INSUFFICIENT_FUNDS"

    @pytest.mark.asyncio
    async def test_process_dlq_event(self) -> None:
        """Test processing DLQ event logs warning."""
        from scripts.sample_consumer import process_event

        event = {
            "event_id": "01HTEST00000000000000003",
            "event_type": "PaymentAuthorized",
            "aggregate_id": "01HPAYMENT00000000003",
            "payload": {},
            "retry_count": 5,
            "error": "max_retries_exceeded",
        }

        await process_event("payments.dlq", event)

        self.mock_logger.warning.assert_called_once()
        call_args = self.mock_logger.warning.call_args
        assert call_args[0][0] == "dead_letter_event_received"
        assert call_args[1]["retry_count"] == 5
        assert call_args[1]["error"] == "max_retries_exceeded"

    @pytest.mark.asyncio
    async def test_process_unknown_event_type(self) -> None:
        """Test processing unknown event type logs appropriately."""
        from scripts.sample_consumer import process_event

        event = {
            "event_id": "01HTEST00000000000000004",
            "event_type": "UnknownEventType",
            "aggregate_id": "01HPAYMENT00000000004",
            "payload": {},
        }

        await process_event("payments.unknowneventtype", event)

        self.mock_logger.info.assert_called_once()
        call_args = self.mock_logger.info.call_args
        assert call_args[0][0] == "unknown_event_received"
        assert call_args[1]["event_type"] == "UnknownEventType"

    @pytest.mark.asyncio
    async def test_process_event_with_missing_payload(self) -> None:
        """Test processing event with missing payload key doesn't crash."""
        from scripts.sample_consumer import process_event

        event = {
            "event_id": "01HTEST00000000000000005",
            "event_type": "PaymentAuthorized",
            "aggregate_id": "01HPAYMENT00000000005",
            # Missing "payload" key
        }

        # Should not raise
        await process_event("payments.paymentauthorized", event)

        # Should log with None values for missing payload fields
        self.mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_event_with_empty_payload(self) -> None:
        """Test processing event with empty payload handles gracefully."""
        from scripts.sample_consumer import process_event

        event = {
            "event_id": "01HTEST00000000000000006",
            "event_type": "PaymentAuthorized",
            "aggregate_id": "01HPAYMENT00000000006",
            "payload": {},
        }

        await process_event("payments.paymentauthorized", event)

        self.mock_logger.info.assert_called_once()
        call_args = self.mock_logger.info.call_args
        assert call_args[1]["payment_id"] is None
        assert call_args[1]["amount_cents"] is None


class TestConsumerTopics:
    """Tests for consumer topic configuration."""

    def test_consumer_topics_include_authorized(self) -> None:
        """Test TOPICS includes payments.paymentauthorized."""
        from scripts.sample_consumer import TOPICS

        assert "payments.paymentauthorized" in TOPICS

    def test_consumer_topics_include_declined(self) -> None:
        """Test TOPICS includes payments.paymentdeclined."""
        from scripts.sample_consumer import TOPICS

        assert "payments.paymentdeclined" in TOPICS

    def test_consumer_topics_include_dlq(self) -> None:
        """Test TOPICS includes payments.dlq."""
        from scripts.sample_consumer import TOPICS

        assert "payments.dlq" in TOPICS

    def test_consumer_topics_count(self) -> None:
        """Test TOPICS has expected number of topics."""
        from scripts.sample_consumer import TOPICS

        assert len(TOPICS) == 3
