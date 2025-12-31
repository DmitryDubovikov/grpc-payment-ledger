"""Integration tests for SlidingWindowRateLimiter with Redis."""

import asyncio

import pytest
import redis.asyncio as redis
from testcontainers.redis import RedisContainer

from payment_service.infrastructure.rate_limiter import SlidingWindowRateLimiter


@pytest.fixture(scope="module")
def redis_container():
    """Start Redis container for tests."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture
async def redis_client(redis_container) -> redis.Redis:
    """Create Redis client connected to container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = redis.from_url(f"redis://{host}:{port}/0")
    yield client
    await client.flushdb()
    await client.close()


class TestSlidingWindowRateLimiterIntegration:
    """Integration tests for SlidingWindowRateLimiter with real Redis."""

    @pytest.mark.asyncio
    async def test_first_request_allowed(self, redis_client: redis.Redis) -> None:
        """Test first request is always allowed."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=10,
            window_seconds=60,
            key_prefix="test:",
        )

        is_allowed, remaining = await limiter.is_allowed("user:first")

        assert is_allowed is True
        assert remaining == 9

    @pytest.mark.asyncio
    async def test_requests_under_limit_allowed(self, redis_client: redis.Redis) -> None:
        """Test requests under limit are allowed."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=5,
            window_seconds=60,
            key_prefix="test:",
        )

        for i in range(5):
            is_allowed, remaining = await limiter.is_allowed("user:under")
            assert is_allowed is True
            assert remaining == 4 - i

    @pytest.mark.asyncio
    async def test_request_at_limit_blocked(self, redis_client: redis.Redis) -> None:
        """Test request at limit is blocked."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=3,
            window_seconds=60,
            key_prefix="test:",
        )

        # Make 3 requests (at limit)
        for _ in range(3):
            is_allowed, _ = await limiter.is_allowed("user:limit")
            assert is_allowed is True

        # 4th request should be blocked
        is_allowed, remaining = await limiter.is_allowed("user:limit")

        assert is_allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_different_identifiers_independent(self, redis_client: redis.Redis) -> None:
        """Test different identifiers are tracked independently."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=2,
            window_seconds=60,
            key_prefix="test:",
        )

        # User A makes 2 requests
        await limiter.is_allowed("user:a")
        await limiter.is_allowed("user:a")

        # User A is now blocked
        is_allowed_a, _ = await limiter.is_allowed("user:a")
        assert is_allowed_a is False

        # User B should still be allowed
        is_allowed_b, remaining_b = await limiter.is_allowed("user:b")
        assert is_allowed_b is True
        assert remaining_b == 1

    @pytest.mark.asyncio
    async def test_get_remaining_accurate(self, redis_client: redis.Redis) -> None:
        """Test get_remaining returns accurate count."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=10,
            window_seconds=60,
            key_prefix="test:",
        )

        # Initially should have all remaining
        remaining = await limiter.get_remaining("user:remaining")
        assert remaining == 10

        # Make some requests
        for _ in range(3):
            await limiter.is_allowed("user:remaining")

        # Should have 7 remaining
        remaining = await limiter.get_remaining("user:remaining")
        assert remaining == 7

    @pytest.mark.asyncio
    async def test_window_expiration(self, redis_client: redis.Redis) -> None:
        """Test requests expire after window."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=2,
            window_seconds=1,  # 1 second window
            key_prefix="test:",
        )

        # Make 2 requests (at limit)
        await limiter.is_allowed("user:expire")
        await limiter.is_allowed("user:expire")

        # Should be blocked
        is_allowed, _ = await limiter.is_allowed("user:expire")
        assert is_allowed is False

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should be allowed again
        is_allowed, remaining = await limiter.is_allowed("user:expire")
        assert is_allowed is True
        assert remaining == 1

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, redis_client: redis.Redis) -> None:
        """Test concurrent requests are handled correctly."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=5,
            window_seconds=60,
            key_prefix="test:",
        )

        async def make_request() -> tuple[bool, int]:
            return await limiter.is_allowed("user:concurrent")

        # Make 10 concurrent requests
        results = await asyncio.gather(*[make_request() for _ in range(10)])

        # Only 5 should be allowed
        allowed_count = sum(1 for is_allowed, _ in results if is_allowed)
        blocked_count = sum(1 for is_allowed, _ in results if not is_allowed)

        assert allowed_count == 5
        assert blocked_count == 5

    @pytest.mark.asyncio
    async def test_sliding_window_behavior(self, redis_client: redis.Redis) -> None:
        """Test sliding window allows gradual recovery."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=3,
            window_seconds=2,  # 2 second window
            key_prefix="test:",
        )

        # Make 3 requests
        for _ in range(3):
            await limiter.is_allowed("user:sliding")

        # Blocked
        is_allowed, _ = await limiter.is_allowed("user:sliding")
        assert is_allowed is False

        # Wait for 1 second (half window)
        await asyncio.sleep(1.1)

        # Still might be blocked or allowed depending on timing
        # Wait full window to be safe
        await asyncio.sleep(1.0)

        # Should be allowed
        is_allowed, _ = await limiter.is_allowed("user:sliding")
        assert is_allowed is True

    @pytest.mark.asyncio
    async def test_key_prefix_isolation(self, redis_client: redis.Redis) -> None:
        """Test different key prefixes are isolated."""
        limiter_a = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=2,
            window_seconds=60,
            key_prefix="prefix_a:",
        )
        limiter_b = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=2,
            window_seconds=60,
            key_prefix="prefix_b:",
        )

        # Exhaust limiter A
        await limiter_a.is_allowed("user:1")
        await limiter_a.is_allowed("user:1")
        is_allowed_a, _ = await limiter_a.is_allowed("user:1")
        assert is_allowed_a is False

        # Limiter B should still work for same user
        is_allowed_b, _ = await limiter_b.is_allowed("user:1")
        assert is_allowed_b is True

    @pytest.mark.asyncio
    async def test_high_volume_requests(self, redis_client: redis.Redis) -> None:
        """Test limiter handles high volume of requests."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=100,
            window_seconds=60,
            key_prefix="test:",
        )

        # Make 150 requests
        allowed = 0
        blocked = 0

        for _i in range(150):
            is_allowed, _ = await limiter.is_allowed("user:highvol")
            if is_allowed:
                allowed += 1
            else:
                blocked += 1

        assert allowed == 100
        assert blocked == 50

    @pytest.mark.asyncio
    async def test_redis_key_ttl(self, redis_client: redis.Redis) -> None:
        """Test Redis keys have correct TTL."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=10,
            window_seconds=30,
            key_prefix="test:",
        )

        await limiter.is_allowed("user:ttl")

        # Check key TTL
        ttl = await redis_client.ttl("test:user:ttl")

        # TTL should be close to window_seconds
        assert 25 <= ttl <= 30

    @pytest.mark.asyncio
    async def test_empty_identifier(self, redis_client: redis.Redis) -> None:
        """Test limiter handles empty identifier."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=5,
            window_seconds=60,
            key_prefix="test:",
        )

        is_allowed, remaining = await limiter.is_allowed("")

        assert is_allowed is True
        assert remaining == 4

    @pytest.mark.asyncio
    async def test_special_characters_in_identifier(self, redis_client: redis.Redis) -> None:
        """Test limiter handles special characters in identifier."""
        limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            max_requests=5,
            window_seconds=60,
            key_prefix="test:",
        )

        is_allowed, _ = await limiter.is_allowed("user:test@example.com")
        assert is_allowed is True

        is_allowed, _ = await limiter.is_allowed("ip:192.168.1.1")
        assert is_allowed is True

        is_allowed, _ = await limiter.is_allowed("method:/api/v1/payments")
        assert is_allowed is True
