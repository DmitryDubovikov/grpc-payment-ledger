from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog


if TYPE_CHECKING:
    import redis.asyncio as redis

logger = structlog.get_logger()


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter using Redis sorted sets.

    Allows `max_requests` per `window_seconds` for each key.
    """

    def __init__(
        self,
        redis_client: "redis.Redis[bytes]",
        max_requests: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "ratelimit:",
    ) -> None:
        self._redis = redis_client
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._key_prefix = key_prefix

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    @property
    def max_requests(self) -> int:
        return self._max_requests

    async def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """
        Check if request is allowed.

        Returns:
            (is_allowed, remaining_requests)
        """
        key = f"{self._key_prefix}{identifier}"
        now = datetime.now(UTC).timestamp()
        window_start = now - self._window_seconds

        pipe = self._redis.pipeline()

        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, self._window_seconds)

        results: list[Any] = await pipe.execute()
        current_count = int(results[1])

        remaining = max(0, self._max_requests - current_count - 1)
        is_allowed = current_count < self._max_requests

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                current_count=current_count,
                max_requests=self._max_requests,
            )

        return is_allowed, remaining

    async def get_remaining(self, identifier: str) -> int:
        """Get remaining requests for identifier."""
        key = f"{self._key_prefix}{identifier}"
        now = datetime.now(UTC).timestamp()
        window_start = now - self._window_seconds

        await self._redis.zremrangebyscore(key, 0, window_start)
        current_count = await self._redis.zcard(key)

        return max(0, self._max_requests - int(current_count))
