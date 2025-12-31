"""Unit tests for SlidingWindowRateLimiter."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from payment_service.infrastructure.rate_limiter import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.pipeline = MagicMock()
        return redis

    @pytest.fixture
    def rate_limiter(self, mock_redis: AsyncMock) -> SlidingWindowRateLimiter:
        """Create rate limiter with mock Redis."""
        return SlidingWindowRateLimiter(
            redis_client=mock_redis,
            max_requests=10,
            window_seconds=60,
            key_prefix="test_ratelimit:",
        )

    def test_init_with_default_values(self, mock_redis: AsyncMock) -> None:
        """Test rate limiter initializes with default values."""
        limiter = SlidingWindowRateLimiter(redis_client=mock_redis)

        assert limiter.max_requests == 100
        assert limiter.window_seconds == 60

    def test_init_with_custom_values(self, mock_redis: AsyncMock) -> None:
        """Test rate limiter initializes with custom values."""
        limiter = SlidingWindowRateLimiter(
            redis_client=mock_redis,
            max_requests=50,
            window_seconds=120,
            key_prefix="custom:",
        )

        assert limiter.max_requests == 50
        assert limiter.window_seconds == 120

    @pytest.mark.asyncio
    async def test_is_allowed_first_request(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test first request is allowed."""
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 0, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, remaining = await rate_limiter.is_allowed("user:123")

        assert is_allowed is True
        assert remaining == 9  # max_requests(10) - current_count(0) - 1

        mock_pipeline.zremrangebyscore.assert_called_once()
        mock_pipeline.zcard.assert_called_once()
        mock_pipeline.zadd.assert_called_once()
        mock_pipeline.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_allowed_under_limit(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test request is allowed when under limit."""
        mock_pipeline = AsyncMock()
        # zremrangebyscore, zcard returns 5, zadd, expire
        mock_pipeline.execute = AsyncMock(return_value=[0, 5, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, remaining = await rate_limiter.is_allowed("user:123")

        assert is_allowed is True
        assert remaining == 4  # max_requests(10) - current_count(5) - 1

    @pytest.mark.asyncio
    async def test_is_allowed_at_limit(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test request is denied when at limit."""
        mock_pipeline = AsyncMock()
        # zremrangebyscore, zcard returns 10 (at limit), zadd, expire
        mock_pipeline.execute = AsyncMock(return_value=[0, 10, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, remaining = await rate_limiter.is_allowed("user:123")

        assert is_allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_is_allowed_over_limit(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test request is denied when over limit."""
        mock_pipeline = AsyncMock()
        # zremrangebyscore, zcard returns 15 (over limit), zadd, expire
        mock_pipeline.execute = AsyncMock(return_value=[0, 15, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, remaining = await rate_limiter.is_allowed("user:123")

        assert is_allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_is_allowed_uses_correct_key(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test rate limiter uses correct key prefix."""
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 0, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        await rate_limiter.is_allowed("user:456")

        # Verify key is used in pipeline calls
        key = "test_ratelimit:user:456"
        mock_pipeline.zcard.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_is_allowed_removes_expired_entries(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test rate limiter removes expired entries from window."""
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[5, 3, 1, True])  # 5 removed
        mock_redis.pipeline.return_value = mock_pipeline

        with patch("payment_service.infrastructure.rate_limiter.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2024, 1, 1, 12, 0, 0)

            await rate_limiter.is_allowed("user:123")

            # Verify zremrangebyscore is called with correct window
            mock_pipeline.zremrangebyscore.assert_called_once()
            call_args = mock_pipeline.zremrangebyscore.call_args
            # Check the window_start is correct (now - window_seconds)
            assert call_args[0][1] == 0  # min score

    @pytest.mark.asyncio
    async def test_is_allowed_sets_expiry(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test rate limiter sets TTL on key."""
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 0, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        await rate_limiter.is_allowed("user:123")

        # Verify expire is called with window_seconds
        mock_pipeline.expire.assert_called_once()
        call_args = mock_pipeline.expire.call_args
        assert call_args[0][1] == 60  # window_seconds

    @pytest.mark.asyncio
    async def test_get_remaining_no_requests(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test get_remaining returns max when no requests made."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)

        remaining = await rate_limiter.get_remaining("user:123")

        assert remaining == 10  # max_requests

    @pytest.mark.asyncio
    async def test_get_remaining_some_requests(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test get_remaining returns correct count."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=7)

        remaining = await rate_limiter.get_remaining("user:123")

        assert remaining == 3  # max_requests(10) - current_count(7)

    @pytest.mark.asyncio
    async def test_get_remaining_at_limit(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test get_remaining returns 0 when at limit."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=10)

        remaining = await rate_limiter.get_remaining("user:123")

        assert remaining == 0

    @pytest.mark.asyncio
    async def test_get_remaining_over_limit(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test get_remaining returns 0 when over limit."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=15)

        remaining = await rate_limiter.get_remaining("user:123")

        assert remaining == 0

    @pytest.mark.asyncio
    async def test_is_allowed_logs_warning_on_rate_limit(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test rate limiter logs warning when limit exceeded."""
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 10, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        with patch("payment_service.infrastructure.rate_limiter.logger") as mock_logger:
            await rate_limiter.is_allowed("user:123")

            mock_logger.warning.assert_called_once_with(
                "rate_limit_exceeded",
                identifier="user:123",
                current_count=10,
                max_requests=10,
            )

    @pytest.mark.asyncio
    async def test_different_identifiers_tracked_separately(
        self,
        rate_limiter: SlidingWindowRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test different identifiers are tracked separately."""
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 0, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        await rate_limiter.is_allowed("user:123")
        await rate_limiter.is_allowed("user:456")

        # Verify different keys are used
        calls = mock_pipeline.zcard.call_args_list
        assert calls[0][0][0] == "test_ratelimit:user:123"
        assert calls[1][0][0] == "test_ratelimit:user:456"


class TestSlidingWindowRateLimiterEdgeCases:
    """Edge case tests for SlidingWindowRateLimiter."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.pipeline = MagicMock()
        return redis

    @pytest.mark.asyncio
    async def test_empty_identifier(self, mock_redis: AsyncMock) -> None:
        """Test rate limiter handles empty identifier."""
        limiter = SlidingWindowRateLimiter(
            redis_client=mock_redis,
            max_requests=10,
            window_seconds=60,
        )

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 0, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, _remaining = await limiter.is_allowed("")

        assert is_allowed is True
        mock_pipeline.zcard.assert_called_once_with("ratelimit:")

    @pytest.mark.asyncio
    async def test_special_characters_in_identifier(self, mock_redis: AsyncMock) -> None:
        """Test rate limiter handles special characters in identifier."""
        limiter = SlidingWindowRateLimiter(
            redis_client=mock_redis,
            max_requests=10,
            window_seconds=60,
        )

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 0, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, _ = await limiter.is_allowed("user:test@example.com:api/v1")

        assert is_allowed is True

    @pytest.mark.asyncio
    async def test_very_small_window(self, mock_redis: AsyncMock) -> None:
        """Test rate limiter with very small window."""
        limiter = SlidingWindowRateLimiter(
            redis_client=mock_redis,
            max_requests=5,
            window_seconds=1,
        )

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 0, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, _ = await limiter.is_allowed("user:123")

        assert is_allowed is True
        mock_pipeline.expire.assert_called_with("ratelimit:user:123", 1)

    @pytest.mark.asyncio
    async def test_very_large_max_requests(self, mock_redis: AsyncMock) -> None:
        """Test rate limiter with very large max requests."""
        limiter = SlidingWindowRateLimiter(
            redis_client=mock_redis,
            max_requests=1000000,
            window_seconds=60,
        )

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 999999, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, remaining = await limiter.is_allowed("user:123")

        assert is_allowed is True
        assert remaining == 0  # 1000000 - 999999 - 1

    @pytest.mark.asyncio
    async def test_single_request_limit(self, mock_redis: AsyncMock) -> None:
        """Test rate limiter with single request limit."""
        limiter = SlidingWindowRateLimiter(
            redis_client=mock_redis,
            max_requests=1,
            window_seconds=60,
        )

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[0, 0, 1, True])
        mock_redis.pipeline.return_value = mock_pipeline

        is_allowed, remaining = await limiter.is_allowed("user:123")

        assert is_allowed is True
        assert remaining == 0  # 1 - 0 - 1 = 0

        # Second request should be denied
        mock_pipeline.execute = AsyncMock(return_value=[0, 1, 1, True])

        is_allowed, remaining = await limiter.is_allowed("user:123")

        assert is_allowed is False
        assert remaining == 0
