"""Integration tests for RedisClient with real Redis."""

import pytest
from testcontainers.redis import RedisContainer

from payment_service.infrastructure.redis_client import RedisClient


@pytest.fixture(scope="module")
def redis_container():
    """Start Redis container for tests."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture
def redis_url(redis_container) -> str:
    """Get Redis URL for container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


class TestRedisClientIntegration:
    """Integration tests for RedisClient with real Redis."""

    @pytest.mark.asyncio
    async def test_connect_success(self, redis_url: str) -> None:
        """Test successful connection to Redis."""
        client = RedisClient(url=redis_url)

        await client.connect()

        assert client._client is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_success(self, redis_url: str) -> None:
        """Test health check returns True when connected."""
        client = RedisClient(url=redis_url)

        await client.connect()
        is_healthy = await client.health_check()

        assert is_healthy is True
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_after_close(self, redis_url: str) -> None:
        """Test health check returns False after close."""
        client = RedisClient(url=redis_url)

        await client.connect()
        await client.close()

        is_healthy = await client.health_check()

        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_basic_operations(self, redis_url: str) -> None:
        """Test basic Redis operations work through client."""
        client = RedisClient(url=redis_url)

        await client.connect()

        # Set and get
        await client.client.set("test_key", "test_value")
        value = await client.client.get("test_key")

        assert value == b"test_value"

        # Clean up
        await client.client.delete("test_key")
        await client.close()

    @pytest.mark.asyncio
    async def test_pipeline_operations(self, redis_url: str) -> None:
        """Test pipeline operations work through client."""
        client = RedisClient(url=redis_url)

        await client.connect()

        # Pipeline operations
        pipe = client.client.pipeline()
        pipe.set("key1", "value1")
        pipe.set("key2", "value2")
        pipe.get("key1")
        pipe.get("key2")
        results = await pipe.execute()

        assert results[2] == b"value1"
        assert results[3] == b"value2"

        # Clean up
        await client.client.delete("key1", "key2")
        await client.close()

    @pytest.mark.asyncio
    async def test_sorted_set_operations(self, redis_url: str) -> None:
        """Test sorted set operations (used by rate limiter)."""
        client = RedisClient(url=redis_url)

        await client.connect()

        key = "test_sorted_set"

        # Add members
        await client.client.zadd(key, {"member1": 1.0, "member2": 2.0, "member3": 3.0})

        # Count members
        count = await client.client.zcard(key)
        assert count == 3

        # Remove by score range
        removed = await client.client.zremrangebyscore(key, 0, 1.5)
        assert removed == 1

        # Verify count
        count = await client.client.zcard(key)
        assert count == 2

        # Clean up
        await client.client.delete(key)
        await client.close()

    @pytest.mark.asyncio
    async def test_expiry_operations(self, redis_url: str) -> None:
        """Test key expiry operations."""
        client = RedisClient(url=redis_url)

        await client.connect()

        key = "test_expiry"
        await client.client.set(key, "value")
        await client.client.expire(key, 10)

        ttl = await client.client.ttl(key)

        assert 5 <= ttl <= 10

        # Clean up
        await client.client.delete(key)
        await client.close()

    @pytest.mark.asyncio
    async def test_reconnect_after_close(self, redis_url: str) -> None:
        """Test client can reconnect after close."""
        client = RedisClient(url=redis_url)

        # First connection
        await client.connect()
        await client.client.set("test_reconnect", "value1")
        await client.close()

        # Second connection
        await client.connect()
        value = await client.client.get("test_reconnect")

        assert value == b"value1"

        # Clean up
        await client.client.delete("test_reconnect")
        await client.close()

    @pytest.mark.asyncio
    async def test_multiple_clients(self, redis_url: str) -> None:
        """Test multiple clients can connect simultaneously."""
        client1 = RedisClient(url=redis_url)
        client2 = RedisClient(url=redis_url)

        await client1.connect()
        await client2.connect()

        # Client 1 sets value
        await client1.client.set("shared_key", "from_client1")

        # Client 2 reads value
        value = await client2.client.get("shared_key")

        assert value == b"from_client1"

        # Clean up
        await client1.client.delete("shared_key")
        await client1.close()
        await client2.close()


class TestRedisClientConnectionFailure:
    """Tests for RedisClient connection failure scenarios."""

    @pytest.mark.asyncio
    async def test_connect_to_invalid_host(self) -> None:
        """Test connection to invalid host fails."""
        client = RedisClient(url="redis://invalid-host:6379/0")

        with pytest.raises(OSError):
            await client.connect()

    @pytest.mark.asyncio
    async def test_connect_to_invalid_port(self, redis_container) -> None:
        """Test connection to invalid port fails."""
        host = redis_container.get_container_host_ip()
        client = RedisClient(url=f"redis://{host}:9999/0")

        with pytest.raises(OSError):
            await client.connect()
