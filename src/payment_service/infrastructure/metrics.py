import time
from collections.abc import Awaitable, Callable
from functools import wraps

from prometheus_client import Counter, Gauge, Histogram


PAYMENT_REQUESTS_TOTAL = Counter(
    "payment_requests_total",
    "Total number of payment requests",
    ["status", "error_code"],
)

RATE_LIMIT_EXCEEDED_TOTAL = Counter(
    "rate_limit_exceeded_total",
    "Total number of rate limited requests",
    ["identifier_type"],
)

OUTBOX_EVENTS_PUBLISHED = Counter(
    "outbox_events_published_total",
    "Total outbox events published",
    ["event_type"],
)

OUTBOX_EVENTS_FAILED = Counter(
    "outbox_events_failed_total",
    "Total outbox events that failed to publish",
    ["event_type"],
)

PAYMENT_DURATION_SECONDS = Histogram(
    "payment_duration_seconds",
    "Payment processing duration",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

GRPC_REQUEST_DURATION = Histogram(
    "grpc_request_duration_seconds",
    "gRPC request duration",
    ["method", "status_code"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

GRPC_REQUESTS_TOTAL = Counter(
    "grpc_requests_total",
    "Total number of gRPC requests",
    ["method", "status_code"],
)

OUTBOX_PENDING_EVENTS = Gauge(
    "outbox_pending_events",
    "Number of pending events in outbox",
)

REDIS_CONNECTIONS_ACTIVE = Gauge(
    "redis_connections_active",
    "Number of active Redis connections",
)

DB_CONNECTIONS_ACTIVE = Gauge(
    "db_connections_active",
    "Number of active database connections",
)


def track_payment_duration[**P, R](
    func: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            duration = time.perf_counter() - start
            PAYMENT_DURATION_SECONDS.observe(duration)

    return wrapper
