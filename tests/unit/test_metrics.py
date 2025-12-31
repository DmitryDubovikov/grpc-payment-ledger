"""Unit tests for metrics module."""

import asyncio
import time
from unittest.mock import patch

import pytest

from payment_service.infrastructure.metrics import (
    DB_CONNECTIONS_ACTIVE,
    GRPC_REQUEST_DURATION,
    GRPC_REQUESTS_TOTAL,
    OUTBOX_EVENTS_FAILED,
    OUTBOX_EVENTS_PUBLISHED,
    OUTBOX_PENDING_EVENTS,
    PAYMENT_DURATION_SECONDS,
    PAYMENT_REQUESTS_TOTAL,
    RATE_LIMIT_EXCEEDED_TOTAL,
    REDIS_CONNECTIONS_ACTIVE,
    track_payment_duration,
)


class TestMetricDefinitions:
    """Tests for metric definitions."""

    def test_payment_requests_total_labels(self) -> None:
        """Test PAYMENT_REQUESTS_TOTAL has correct labels."""
        assert "status" in PAYMENT_REQUESTS_TOTAL._labelnames
        assert "error_code" in PAYMENT_REQUESTS_TOTAL._labelnames

    def test_rate_limit_exceeded_total_labels(self) -> None:
        """Test RATE_LIMIT_EXCEEDED_TOTAL has correct labels."""
        assert "identifier_type" in RATE_LIMIT_EXCEEDED_TOTAL._labelnames

    def test_outbox_events_published_labels(self) -> None:
        """Test OUTBOX_EVENTS_PUBLISHED has correct labels."""
        assert "event_type" in OUTBOX_EVENTS_PUBLISHED._labelnames

    def test_outbox_events_failed_labels(self) -> None:
        """Test OUTBOX_EVENTS_FAILED has correct labels."""
        assert "event_type" in OUTBOX_EVENTS_FAILED._labelnames

    def test_payment_duration_seconds_buckets(self) -> None:
        """Test PAYMENT_DURATION_SECONDS has correct buckets."""
        expected_buckets = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        # prometheus_client adds +Inf bucket automatically
        assert list(PAYMENT_DURATION_SECONDS._upper_bounds[:-1]) == expected_buckets

    def test_grpc_request_duration_labels(self) -> None:
        """Test GRPC_REQUEST_DURATION has correct labels."""
        assert "method" in GRPC_REQUEST_DURATION._labelnames
        assert "status_code" in GRPC_REQUEST_DURATION._labelnames

    def test_grpc_request_duration_buckets(self) -> None:
        """Test GRPC_REQUEST_DURATION has correct buckets."""
        expected_buckets = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        assert list(GRPC_REQUEST_DURATION._upper_bounds[:-1]) == expected_buckets

    def test_grpc_requests_total_labels(self) -> None:
        """Test GRPC_REQUESTS_TOTAL has correct labels."""
        assert "method" in GRPC_REQUESTS_TOTAL._labelnames
        assert "status_code" in GRPC_REQUESTS_TOTAL._labelnames

    def test_outbox_pending_events_is_gauge(self) -> None:
        """Test OUTBOX_PENDING_EVENTS is a gauge."""
        # Gauge has set method
        assert hasattr(OUTBOX_PENDING_EVENTS, "set")

    def test_redis_connections_active_is_gauge(self) -> None:
        """Test REDIS_CONNECTIONS_ACTIVE is a gauge."""
        assert hasattr(REDIS_CONNECTIONS_ACTIVE, "set")

    def test_db_connections_active_is_gauge(self) -> None:
        """Test DB_CONNECTIONS_ACTIVE is a gauge."""
        assert hasattr(DB_CONNECTIONS_ACTIVE, "set")


class TestTrackPaymentDuration:
    """Tests for track_payment_duration decorator."""

    @pytest.mark.asyncio
    async def test_decorator_returns_result(self) -> None:
        """Test decorator returns function result."""

        @track_payment_duration
        async def sample_function() -> str:
            return "result"

        result = await sample_function()

        assert result == "result"

    @pytest.mark.asyncio
    async def test_decorator_observes_duration(self) -> None:
        """Test decorator observes duration to histogram."""
        with patch("payment_service.infrastructure.metrics.PAYMENT_DURATION_SECONDS") as mock_histogram:

            @track_payment_duration
            async def sample_function() -> str:
                await asyncio.sleep(0.01)
                return "result"

            await sample_function()

            mock_histogram.observe.assert_called_once()
            duration = mock_histogram.observe.call_args[0][0]
            assert duration >= 0.01

    @pytest.mark.asyncio
    async def test_decorator_observes_duration_on_exception(self) -> None:
        """Test decorator observes duration even on exception."""
        with patch("payment_service.infrastructure.metrics.PAYMENT_DURATION_SECONDS") as mock_histogram:

            @track_payment_duration
            async def failing_function() -> str:
                await asyncio.sleep(0.01)
                raise ValueError("Test error")

            with pytest.raises(ValueError, match="Test error"):
                await failing_function()

            mock_histogram.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_name(self) -> None:
        """Test decorator preserves original function name."""

        @track_payment_duration
        async def my_special_function() -> str:
            return "result"

        assert my_special_function.__name__ == "my_special_function"

    @pytest.mark.asyncio
    async def test_decorator_preserves_docstring(self) -> None:
        """Test decorator preserves original function docstring."""

        @track_payment_duration
        async def documented_function() -> str:
            """This is my docstring."""
            return "result"

        assert documented_function.__doc__ == "This is my docstring."

    @pytest.mark.asyncio
    async def test_decorator_with_arguments(self) -> None:
        """Test decorator works with function arguments."""

        @track_payment_duration
        async def function_with_args(x: int, y: str, z: bool = True) -> tuple:
            return (x, y, z)

        result = await function_with_args(1, "test", z=False)

        assert result == (1, "test", False)

    @pytest.mark.asyncio
    async def test_decorator_measures_accurate_duration(self) -> None:
        """Test decorator measures duration accurately."""
        observed_duration = None

        def capture_duration(duration: float) -> None:
            nonlocal observed_duration
            observed_duration = duration

        with patch("payment_service.infrastructure.metrics.PAYMENT_DURATION_SECONDS") as mock_histogram:
            mock_histogram.observe = capture_duration

            @track_payment_duration
            async def timed_function() -> str:
                await asyncio.sleep(0.05)
                return "result"

            start = time.perf_counter()
            await timed_function()
            actual_duration = time.perf_counter() - start

            # Duration should be close to actual execution time
            assert observed_duration is not None
            assert abs(observed_duration - actual_duration) < 0.01


class TestMetricUsage:
    """Tests for metric usage patterns."""

    def test_counter_increment(self) -> None:
        """Test counter can be incremented with labels."""
        # Just verify the API works, don't check actual values
        PAYMENT_REQUESTS_TOTAL.labels(status="AUTHORIZED", error_code="").inc()

    def test_counter_increment_by_amount(self) -> None:
        """Test counter can be incremented by specific amount."""
        PAYMENT_REQUESTS_TOTAL.labels(status="DECLINED", error_code="INSUFFICIENT_FUNDS").inc(5)

    def test_histogram_observe(self) -> None:
        """Test histogram can observe values."""
        PAYMENT_DURATION_SECONDS.observe(0.123)

    def test_histogram_with_labels_observe(self) -> None:
        """Test histogram with labels can observe values."""
        GRPC_REQUEST_DURATION.labels(
            method="/payment.v1.PaymentService/AuthorizePayment",
            status_code="OK",
        ).observe(0.05)

    def test_gauge_set(self) -> None:
        """Test gauge can set values."""
        OUTBOX_PENDING_EVENTS.set(42)

    def test_gauge_inc_dec(self) -> None:
        """Test gauge can increment and decrement."""
        REDIS_CONNECTIONS_ACTIVE.inc()
        REDIS_CONNECTIONS_ACTIVE.dec()

    def test_rate_limit_counter_with_identifier_types(self) -> None:
        """Test rate limit counter with different identifier types."""
        RATE_LIMIT_EXCEEDED_TOTAL.labels(identifier_type="client").inc()
        RATE_LIMIT_EXCEEDED_TOTAL.labels(identifier_type="ip").inc()
        RATE_LIMIT_EXCEEDED_TOTAL.labels(identifier_type="method").inc()

    def test_outbox_events_with_event_types(self) -> None:
        """Test outbox event counters with different event types."""
        OUTBOX_EVENTS_PUBLISHED.labels(event_type="PaymentAuthorized").inc()
        OUTBOX_EVENTS_PUBLISHED.labels(event_type="PaymentDeclined").inc()
        OUTBOX_EVENTS_FAILED.labels(event_type="PaymentAuthorized").inc()


class TestMetricDescriptions:
    """Tests for metric descriptions and metadata."""

    def test_payment_requests_total_description(self) -> None:
        """Test PAYMENT_REQUESTS_TOTAL has description."""
        assert PAYMENT_REQUESTS_TOTAL._documentation == "Total number of payment requests"

    def test_rate_limit_exceeded_description(self) -> None:
        """Test RATE_LIMIT_EXCEEDED_TOTAL has description."""
        assert RATE_LIMIT_EXCEEDED_TOTAL._documentation == "Total number of rate limited requests"

    def test_payment_duration_description(self) -> None:
        """Test PAYMENT_DURATION_SECONDS has description."""
        assert PAYMENT_DURATION_SECONDS._documentation == "Payment processing duration"

    def test_grpc_request_duration_description(self) -> None:
        """Test GRPC_REQUEST_DURATION has description."""
        assert GRPC_REQUEST_DURATION._documentation == "gRPC request duration"

    def test_outbox_pending_description(self) -> None:
        """Test OUTBOX_PENDING_EVENTS has description."""
        assert OUTBOX_PENDING_EVENTS._documentation == "Number of pending events in outbox"
