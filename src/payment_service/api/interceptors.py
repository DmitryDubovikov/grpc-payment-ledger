import time
from collections.abc import Callable
from typing import Any

import grpc
import structlog

from payment_service.infrastructure.metrics import (
    GRPC_REQUEST_DURATION,
    GRPC_REQUESTS_TOTAL,
    RATE_LIMIT_EXCEEDED_TOTAL,
)
from payment_service.infrastructure.rate_limiter import SlidingWindowRateLimiter


logger = structlog.get_logger()


class MetricsInterceptor(grpc.aio.ServerInterceptor):
    """gRPC interceptor that collects Prometheus metrics."""

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Any],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        method = handler_call_details.method
        start_time = time.perf_counter()
        status_code = "OK"

        try:
            handler = await continuation(handler_call_details)
            return handler
        except grpc.RpcError as e:
            status_code = e.code().name if hasattr(e, "code") else "UNKNOWN"
            raise
        except Exception:
            status_code = "UNKNOWN"
            raise
        finally:
            duration = time.perf_counter() - start_time
            GRPC_REQUEST_DURATION.labels(method=method, status_code=status_code).observe(duration)
            GRPC_REQUESTS_TOTAL.labels(method=method, status_code=status_code).inc()


class RateLimitInterceptor(grpc.aio.ServerInterceptor):
    """gRPC interceptor that enforces rate limiting."""

    def __init__(self, rate_limiter: SlidingWindowRateLimiter) -> None:
        self._rate_limiter = rate_limiter

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Any],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        method = handler_call_details.method

        if self._should_skip_rate_limiting(method):
            return await continuation(handler_call_details)

        identifier = self._get_identifier(handler_call_details)
        is_allowed, _remaining = await self._rate_limiter.is_allowed(identifier)

        if not is_allowed:
            RATE_LIMIT_EXCEEDED_TOTAL.labels(identifier_type="method").inc()
            logger.warning(
                "rate_limit_exceeded",
                method=method,
                identifier=identifier,
            )
            raise _create_rate_limit_error(self._rate_limiter.window_seconds)

        return await continuation(handler_call_details)

    def _should_skip_rate_limiting(self, method: str) -> bool:
        """Skip rate limiting for health checks and reflection."""
        skip_prefixes = (
            "/grpc.health.v1.Health/",
            "/grpc.reflection.v1alpha.",
            "/grpc.reflection.v1.",
        )
        return any(method.startswith(prefix) for prefix in skip_prefixes)

    def _get_identifier(self, handler_call_details: grpc.HandlerCallDetails) -> str:
        """Extract identifier from request metadata or use method name."""
        metadata = dict(handler_call_details.invocation_metadata or [])

        if client_id := metadata.get("x-client-id"):
            return f"client:{client_id}"

        if ip := metadata.get("x-forwarded-for"):
            return f"ip:{ip.split(',')[0].strip()}"

        return f"method:{handler_call_details.method}"


def _create_rate_limit_error(retry_after: int) -> grpc.RpcError:
    """Create a rate limit exceeded error."""
    return grpc.aio.AbortError(
        grpc.StatusCode.RESOURCE_EXHAUSTED,
        f"Rate limit exceeded. Retry after {retry_after}s",
    )
