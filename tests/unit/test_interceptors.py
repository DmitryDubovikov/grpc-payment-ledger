"""Unit tests for gRPC interceptors."""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from payment_service.api.interceptors import (
    MetricsInterceptor,
    RateLimitInterceptor,
    _create_rate_limit_error,
)
from payment_service.infrastructure.rate_limiter import SlidingWindowRateLimiter


class TestMetricsInterceptor:
    """Tests for MetricsInterceptor."""

    @pytest.fixture
    def interceptor(self) -> MetricsInterceptor:
        """Create MetricsInterceptor instance."""
        return MetricsInterceptor()

    @pytest.fixture
    def mock_handler_call_details(self) -> MagicMock:
        """Create mock handler call details."""
        details = MagicMock(spec=grpc.HandlerCallDetails)
        details.method = "/payment.v1.PaymentService/AuthorizePayment"
        details.invocation_metadata = []
        return details

    @pytest.fixture
    def mock_continuation(self) -> AsyncMock:
        """Create mock continuation function."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_intercept_records_duration(
        self,
        interceptor: MetricsInterceptor,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor records request duration."""
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        with patch("payment_service.api.interceptors.GRPC_REQUEST_DURATION") as mock_histogram:
            await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

            mock_histogram.labels.assert_called_with(
                method="/payment.v1.PaymentService/AuthorizePayment",
                status_code="OK",
            )
            mock_histogram.labels.return_value.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_intercept_increments_request_counter(
        self,
        interceptor: MetricsInterceptor,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor increments request counter."""
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        with patch("payment_service.api.interceptors.GRPC_REQUESTS_TOTAL") as mock_counter:
            await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

            mock_counter.labels.assert_called_with(
                method="/payment.v1.PaymentService/AuthorizePayment",
                status_code="OK",
            )
            mock_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_intercept_returns_handler(
        self,
        interceptor: MetricsInterceptor,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor returns handler from continuation."""
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        result = await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

        assert result is mock_handler

    @pytest.mark.asyncio
    async def test_intercept_handles_rpc_error(
        self,
        interceptor: MetricsInterceptor,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor handles RPC error and records status."""

        class MockRpcError(grpc.RpcError):
            def code(self) -> grpc.StatusCode:
                return grpc.StatusCode.NOT_FOUND

        mock_error = MockRpcError()
        mock_continuation.side_effect = mock_error

        with patch("payment_service.api.interceptors.GRPC_REQUEST_DURATION") as mock_histogram:
            with pytest.raises(grpc.RpcError):
                await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

            mock_histogram.labels.assert_called_with(
                method="/payment.v1.PaymentService/AuthorizePayment",
                status_code="NOT_FOUND",
            )

    @pytest.mark.asyncio
    async def test_intercept_handles_unknown_exception(
        self,
        interceptor: MetricsInterceptor,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor handles unknown exception."""
        mock_continuation.side_effect = ValueError("Unknown error")

        with patch("payment_service.api.interceptors.GRPC_REQUEST_DURATION") as mock_histogram:
            with pytest.raises(ValueError, match="Unknown error"):
                await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

            mock_histogram.labels.assert_called_with(
                method="/payment.v1.PaymentService/AuthorizePayment",
                status_code="UNKNOWN",
            )

    @pytest.mark.asyncio
    async def test_intercept_records_positive_duration(
        self,
        interceptor: MetricsInterceptor,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor records positive duration."""
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        observed_duration = None

        def capture_duration(duration: float) -> None:
            nonlocal observed_duration
            observed_duration = duration

        with patch("payment_service.api.interceptors.GRPC_REQUEST_DURATION") as mock_histogram:
            mock_histogram.labels.return_value.observe = capture_duration

            await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

            assert observed_duration is not None
            assert observed_duration >= 0


class TestRateLimitInterceptor:
    """Tests for RateLimitInterceptor."""

    @pytest.fixture
    def mock_rate_limiter(self) -> AsyncMock:
        """Create mock rate limiter."""
        limiter = AsyncMock(spec=SlidingWindowRateLimiter)
        limiter.window_seconds = 60
        return limiter

    @pytest.fixture
    def interceptor(self, mock_rate_limiter: AsyncMock) -> RateLimitInterceptor:
        """Create RateLimitInterceptor instance."""
        return RateLimitInterceptor(rate_limiter=mock_rate_limiter)

    @pytest.fixture
    def mock_handler_call_details(self) -> MagicMock:
        """Create mock handler call details."""
        details = MagicMock(spec=grpc.HandlerCallDetails)
        details.method = "/payment.v1.PaymentService/AuthorizePayment"
        details.invocation_metadata = []
        return details

    @pytest.fixture
    def mock_continuation(self) -> AsyncMock:
        """Create mock continuation function."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_intercept_allows_request_under_limit(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor allows request when under rate limit."""
        mock_rate_limiter.is_allowed.return_value = (True, 99)
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        result = await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

        assert result is mock_handler
        mock_continuation.assert_called_once_with(mock_handler_call_details)

    @pytest.mark.asyncio
    async def test_intercept_blocks_request_over_limit(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor blocks request when over rate limit."""
        mock_rate_limiter.is_allowed.return_value = (False, 0)

        with pytest.raises(grpc.aio.AbortError):
            await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

        mock_continuation.assert_not_called()

    @pytest.mark.asyncio
    async def test_intercept_increments_rate_limit_counter(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor increments rate limit counter on block."""
        mock_rate_limiter.is_allowed.return_value = (False, 0)

        with patch("payment_service.api.interceptors.RATE_LIMIT_EXCEEDED_TOTAL") as mock_counter:
            with pytest.raises(grpc.aio.AbortError):
                await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

            mock_counter.labels.assert_called_with(identifier_type="method")
            mock_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_intercept_skips_health_check(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor skips rate limiting for health checks."""
        details = MagicMock(spec=grpc.HandlerCallDetails)
        details.method = "/grpc.health.v1.Health/Check"
        details.invocation_metadata = []

        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        result = await interceptor.intercept_service(mock_continuation, details)

        assert result is mock_handler
        mock_rate_limiter.is_allowed.assert_not_called()

    @pytest.mark.asyncio
    async def test_intercept_skips_reflection(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor skips rate limiting for reflection."""
        details = MagicMock(spec=grpc.HandlerCallDetails)
        details.method = "/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo"
        details.invocation_metadata = []

        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        result = await interceptor.intercept_service(mock_continuation, details)

        assert result is mock_handler
        mock_rate_limiter.is_allowed.assert_not_called()

    @pytest.mark.asyncio
    async def test_intercept_skips_reflection_v1(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor skips rate limiting for reflection v1."""
        details = MagicMock(spec=grpc.HandlerCallDetails)
        details.method = "/grpc.reflection.v1.ServerReflection/ServerReflectionInfo"
        details.invocation_metadata = []

        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        result = await interceptor.intercept_service(mock_continuation, details)

        assert result is mock_handler
        mock_rate_limiter.is_allowed.assert_not_called()

    @pytest.mark.asyncio
    async def test_intercept_uses_client_id_from_metadata(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor uses client ID from metadata."""
        mock_handler_call_details.invocation_metadata = [
            ("x-client-id", "client-123"),
        ]
        mock_rate_limiter.is_allowed.return_value = (True, 99)
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

        mock_rate_limiter.is_allowed.assert_called_with("client:client-123")

    @pytest.mark.asyncio
    async def test_intercept_uses_ip_from_metadata(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor uses IP from x-forwarded-for metadata."""
        mock_handler_call_details.invocation_metadata = [
            ("x-forwarded-for", "192.168.1.1, 10.0.0.1"),
        ]
        mock_rate_limiter.is_allowed.return_value = (True, 99)
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

        # Should use first IP from x-forwarded-for
        mock_rate_limiter.is_allowed.assert_called_with("ip:192.168.1.1")

    @pytest.mark.asyncio
    async def test_intercept_uses_method_as_fallback(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor uses method as fallback identifier."""
        mock_handler_call_details.invocation_metadata = []
        mock_rate_limiter.is_allowed.return_value = (True, 99)
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

        mock_rate_limiter.is_allowed.assert_called_with("method:/payment.v1.PaymentService/AuthorizePayment")

    @pytest.mark.asyncio
    async def test_intercept_logs_warning_on_rate_limit(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test interceptor logs warning when rate limited."""
        mock_rate_limiter.is_allowed.return_value = (False, 0)

        with patch("payment_service.api.interceptors.logger") as mock_logger:
            with pytest.raises(grpc.aio.AbortError):
                await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

            mock_logger.warning.assert_called_once_with(
                "rate_limit_exceeded",
                method="/payment.v1.PaymentService/AuthorizePayment",
                identifier="method:/payment.v1.PaymentService/AuthorizePayment",
            )

    @pytest.mark.asyncio
    async def test_intercept_client_id_takes_precedence_over_ip(
        self,
        interceptor: RateLimitInterceptor,
        mock_rate_limiter: AsyncMock,
        mock_handler_call_details: MagicMock,
        mock_continuation: AsyncMock,
    ) -> None:
        """Test client ID takes precedence over IP for identifier."""
        mock_handler_call_details.invocation_metadata = [
            ("x-client-id", "client-456"),
            ("x-forwarded-for", "192.168.1.1"),
        ]
        mock_rate_limiter.is_allowed.return_value = (True, 99)
        mock_handler = MagicMock()
        mock_continuation.return_value = mock_handler

        await interceptor.intercept_service(mock_continuation, mock_handler_call_details)

        mock_rate_limiter.is_allowed.assert_called_with("client:client-456")


class TestCreateRateLimitError:
    """Tests for _create_rate_limit_error helper."""

    def test_creates_abort_error(self) -> None:
        """Test helper creates AbortError."""
        error = _create_rate_limit_error(60)

        assert isinstance(error, grpc.aio.AbortError)

    def test_error_has_resource_exhausted_code(self) -> None:
        """Test error has RESOURCE_EXHAUSTED status code."""
        error = _create_rate_limit_error(60)

        # AbortError stores code as first arg
        assert error.args[0] == grpc.StatusCode.RESOURCE_EXHAUSTED

    def test_error_includes_retry_after(self) -> None:
        """Test error message includes retry after."""
        error = _create_rate_limit_error(120)

        assert "120s" in error.args[1]

    def test_error_message_format(self) -> None:
        """Test error message format."""
        error = _create_rate_limit_error(30)

        assert error.args[1] == "Rate limit exceeded. Retry after 30s"
