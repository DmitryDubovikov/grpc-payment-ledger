"""Unit tests for RedisClient."""

from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as redis

from payment_service.infrastructure.redis_client import RedisClient


class TestRedisClient:
    """Tests for RedisClient."""

    def test_init_with_default_url(self) -> None:
        """Test RedisClient initializes with default URL from settings."""
        with patch("payment_service.infrastructure.redis_client.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"

            client = RedisClient()

            assert client._url == "redis://localhost:6379/0"

    def test_init_with_custom_url(self) -> None:
        """Test RedisClient initializes with custom URL."""
        client = RedisClient(url="redis://custom-host:6380/1")

        assert client._url == "redis://custom-host:6380/1"

    def test_client_property_raises_when_not_connected(self) -> None:
        """Test client property raises RuntimeError when not connected."""
        client = RedisClient(url="redis://localhost:6379/0")

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            _ = client.client

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful Redis connection."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch(
            "payment_service.infrastructure.redis_client.redis.from_url",
            return_value=mock_redis,
        ) as mock_from_url:
            await client.connect()

            mock_from_url.assert_called_once_with(
                "redis://localhost:6379/0",
                encoding="utf-8",
                decode_responses=False,
            )
            mock_redis.ping.assert_called_once()
            assert client._client is mock_redis

    @pytest.mark.asyncio
    async def test_connect_logs_success(self) -> None:
        """Test connect logs success message."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch(
                "payment_service.infrastructure.redis_client.redis.from_url",
                return_value=mock_redis,
            ),
            patch("payment_service.infrastructure.redis_client.logger") as mock_logger,
        ):
            await client.connect()

            mock_logger.info.assert_called_once_with("redis_connected", url="redis://localhost:6379/0")

    @pytest.mark.asyncio
    async def test_client_property_after_connect(self) -> None:
        """Test client property returns Redis client after connection."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch(
            "payment_service.infrastructure.redis_client.redis.from_url",
            return_value=mock_redis,
        ):
            await client.connect()

            assert client.client is mock_redis

    @pytest.mark.asyncio
    async def test_close_success(self) -> None:
        """Test successful Redis connection close."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.close = AsyncMock()

        with patch(
            "payment_service.infrastructure.redis_client.redis.from_url",
            return_value=mock_redis,
        ):
            await client.connect()
            await client.close()

            mock_redis.close.assert_called_once()
            assert client._client is None

    @pytest.mark.asyncio
    async def test_close_logs_success(self) -> None:
        """Test close logs success message."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.close = AsyncMock()

        with patch(
            "payment_service.infrastructure.redis_client.redis.from_url",
            return_value=mock_redis,
        ):
            await client.connect()

            with patch("payment_service.infrastructure.redis_client.logger") as mock_logger:
                await client.close()

                mock_logger.info.assert_called_once_with("redis_disconnected")

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self) -> None:
        """Test close does nothing when not connected."""
        client = RedisClient(url="redis://localhost:6379/0")

        # Should not raise
        await client.close()

        assert client._client is None

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """Test health check returns True when Redis is healthy."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch(
            "payment_service.infrastructure.redis_client.redis.from_url",
            return_value=mock_redis,
        ):
            await client.connect()

            is_healthy = await client.health_check()

            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        """Test health check returns False when Redis is unhealthy."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=redis.RedisError("Connection lost"))

        with patch(
            "payment_service.infrastructure.redis_client.redis.from_url",
            return_value=mock_redis,
        ):
            # Manually set client to simulate connection
            client._client = mock_redis

            is_healthy = await client.health_check()

            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_health_check_when_not_connected(self) -> None:
        """Test health check returns False when not connected."""
        client = RedisClient(url="redis://localhost:6379/0")

        is_healthy = await client.health_check()

        assert is_healthy is False


class TestRedisClientIntegrationPatterns:
    """Tests for RedisClient usage patterns."""

    @pytest.mark.asyncio
    async def test_connect_close_cycle(self) -> None:
        """Test multiple connect/close cycles."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.close = AsyncMock()

        with patch(
            "payment_service.infrastructure.redis_client.redis.from_url",
            return_value=mock_redis,
        ):
            # First cycle
            await client.connect()
            assert client._client is not None
            await client.close()
            assert client._client is None

            # Second cycle
            await client.connect()
            assert client._client is not None
            await client.close()
            assert client._client is None

    @pytest.mark.asyncio
    async def test_client_can_be_used_for_operations(self) -> None:
        """Test client can be used for Redis operations after connection."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=b"value")
        mock_redis.set = AsyncMock(return_value=True)

        with patch(
            "payment_service.infrastructure.redis_client.redis.from_url",
            return_value=mock_redis,
        ):
            await client.connect()

            # Use client for operations
            await client.client.set("key", "value")
            result = await client.client.get("key")

            mock_redis.set.assert_called_once_with("key", "value")
            mock_redis.get.assert_called_once_with("key")
            assert result == b"value"

    @pytest.mark.asyncio
    async def test_health_check_with_connection_timeout(self) -> None:
        """Test health check handles connection timeout."""
        client = RedisClient(url="redis://localhost:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=redis.RedisError("Connection timed out"))

        client._client = mock_redis

        is_healthy = await client.health_check()

        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_connect_with_ping_failure(self) -> None:
        """Test connect propagates ping failure."""
        client = RedisClient(url="redis://invalid-host:6379/0")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=redis.RedisError("Cannot connect"))

        with (
            patch(
                "payment_service.infrastructure.redis_client.redis.from_url",
                return_value=mock_redis,
            ),
            pytest.raises(redis.RedisError, match="Cannot connect"),
        ):
            await client.connect()
