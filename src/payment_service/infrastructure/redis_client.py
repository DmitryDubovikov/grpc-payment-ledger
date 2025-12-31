import redis.asyncio as redis
import structlog

from payment_service.config import settings


logger = structlog.get_logger()


class RedisClient:
    """Async Redis client wrapper."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.redis_url
        self._client: redis.Redis[bytes] | None = None

    @property
    def client(self) -> "redis.Redis[bytes]":
        """Get the Redis client. Raises if not connected."""
        if self._client is None:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._client

    async def connect(self) -> None:
        """Connect to Redis."""
        self._client = redis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=False,
        )
        await self._client.ping()
        logger.info("redis_connected", url=self._url)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("redis_disconnected")

    async def health_check(self) -> bool:
        """Check if Redis is healthy."""
        try:
            if self._client:
                await self._client.ping()
                return True
        except redis.RedisError:
            pass
        return False
