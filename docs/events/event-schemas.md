# Event Schemas

This document describes the event schemas published by the Payment Service via the Outbox Pattern.

## Overview

The Payment Service publishes domain events to Kafka/Redpanda when payments are processed. Events are written to the `outbox` table within the same database transaction as the payment, ensuring exactly-once delivery semantics.

### Event Flow

```
Payment Request
       │
       ▼
┌──────────────────┐
│ PaymentService   │
│                  │
│ 1. Validate      │
│ 2. Create Payment│
│ 3. Update Ledger │
│ 4. Write Outbox  │◄─── Same DB Transaction
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  outbox table    │
│                  │
│ published_at=NULL│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ OutboxProcessor  │
│                  │
│ 1. Poll unpub.   │
│ 2. Publish Kafka │
│ 3. Mark published│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Kafka Topic     │
│                  │
│ payments.*       │
└──────────────────┘
```

---

## Event Envelope

All events share a common envelope structure:

```json
{
  "event_id": "01HYABCDEF1234567890QRST",
  "aggregate_type": "Payment",
  "aggregate_id": "01HYABCDEF1234567890QRST",
  "event_type": "PaymentAuthorized",
  "payload": { ... },
  "timestamp": "2024-01-15T10:30:00.123456+00:00"
}
```

### Envelope Fields

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | string | Unique event identifier (ULID) |
| `aggregate_type` | string | Type of aggregate that produced the event |
| `aggregate_id` | string | ID of the aggregate (e.g., payment_id) |
| `event_type` | string | Type of domain event |
| `payload` | object | Event-specific data |
| `timestamp` | string | ISO 8601 timestamp when event was created |

---

## PaymentAuthorized Event

Published when a payment is successfully authorized.

**Topic**: `payments.paymentauthorized`

### Schema (JSON Schema)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PaymentAuthorized",
  "type": "object",
  "required": ["event_id", "aggregate_type", "aggregate_id", "event_type", "payload", "timestamp"],
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Unique event identifier (ULID)",
      "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"
    },
    "aggregate_type": {
      "type": "string",
      "const": "Payment"
    },
    "aggregate_id": {
      "type": "string",
      "description": "Payment ID (ULID)"
    },
    "event_type": {
      "type": "string",
      "const": "PaymentAuthorized"
    },
    "payload": {
      "type": "object",
      "required": ["payment_id", "payer_account_id", "payee_account_id", "amount_cents", "currency"],
      "properties": {
        "payment_id": {
          "type": "string",
          "description": "Payment ID (ULID)"
        },
        "payer_account_id": {
          "type": "string",
          "description": "Payer account ID"
        },
        "payee_account_id": {
          "type": "string",
          "description": "Payee account ID"
        },
        "amount_cents": {
          "type": "integer",
          "minimum": 1,
          "description": "Amount in cents"
        },
        "currency": {
          "type": "string",
          "pattern": "^[A-Z]{3}$",
          "description": "ISO 4217 currency code"
        }
      }
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

### Example

```json
{
  "event_id": "01HYABCDEF1234567890QRST",
  "aggregate_type": "Payment",
  "aggregate_id": "01HYABCDEF1234567890QRST",
  "event_type": "PaymentAuthorized",
  "payload": {
    "payment_id": "01HYABCDEF1234567890QRST",
    "payer_account_id": "01HY1234567890ABCDEFGHIJ",
    "payee_account_id": "01HY0987654321JIHGFEDCBA",
    "amount_cents": 5000,
    "currency": "USD"
  },
  "timestamp": "2024-01-15T10:30:00.123456+00:00"
}
```

---

## PaymentDeclined Event

Published when a payment is declined (insufficient funds, account not found, etc.).

**Topic**: `payments.paymentdeclined`

### Schema (JSON Schema)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PaymentDeclined",
  "type": "object",
  "required": ["event_id", "aggregate_type", "aggregate_id", "event_type", "payload", "timestamp"],
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Unique event identifier (ULID)"
    },
    "aggregate_type": {
      "type": "string",
      "const": "Payment"
    },
    "aggregate_id": {
      "type": "string",
      "description": "Payment ID (ULID)"
    },
    "event_type": {
      "type": "string",
      "const": "PaymentDeclined"
    },
    "payload": {
      "type": "object",
      "required": ["payment_id", "payer_account_id", "error_code"],
      "properties": {
        "payment_id": {
          "type": "string",
          "description": "Payment ID (ULID)"
        },
        "payer_account_id": {
          "type": "string",
          "description": "Payer account ID"
        },
        "payee_account_id": {
          "type": "string",
          "description": "Payee account ID"
        },
        "amount_cents": {
          "type": "integer",
          "description": "Requested amount in cents"
        },
        "currency": {
          "type": "string",
          "description": "ISO 4217 currency code"
        },
        "error_code": {
          "type": "string",
          "enum": [
            "INSUFFICIENT_FUNDS",
            "ACCOUNT_NOT_FOUND",
            "INVALID_AMOUNT",
            "SAME_ACCOUNT",
            "CURRENCY_MISMATCH",
            "RATE_LIMITED"
          ],
          "description": "Error code indicating reason for decline"
        },
        "error_message": {
          "type": "string",
          "description": "Human-readable error message"
        }
      }
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

### Example

```json
{
  "event_id": "01HYXYZ123456789ABCDEFGH",
  "aggregate_type": "Payment",
  "aggregate_id": "01HYXYZ123456789ABCDEFGH",
  "event_type": "PaymentDeclined",
  "payload": {
    "payment_id": "01HYXYZ123456789ABCDEFGH",
    "payer_account_id": "01HY1234567890ABCDEFGHIJ",
    "payee_account_id": "01HY0987654321JIHGFEDCBA",
    "amount_cents": 999999999,
    "currency": "USD",
    "error_code": "INSUFFICIENT_FUNDS",
    "error_message": "Insufficient funds"
  },
  "timestamp": "2024-01-15T10:35:00.123456+00:00"
}
```

---

## Dead Letter Queue Event

Events that fail to publish after max retries are sent to the Dead Letter Queue.

**Topic**: `payments.dlq`

### Schema

DLQ events include additional metadata about the failure:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DeadLetterEvent",
  "type": "object",
  "required": ["event_id", "aggregate_type", "aggregate_id", "event_type", "payload", "timestamp", "retry_count", "failed_at", "error"],
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Original event ID"
    },
    "aggregate_type": {
      "type": "string"
    },
    "aggregate_id": {
      "type": "string"
    },
    "event_type": {
      "type": "string",
      "description": "Original event type"
    },
    "payload": {
      "type": "object",
      "description": "Original event payload"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "Original event timestamp"
    },
    "retry_count": {
      "type": "integer",
      "description": "Number of retry attempts"
    },
    "failed_at": {
      "type": "string",
      "format": "date-time",
      "description": "When the event was moved to DLQ"
    },
    "error": {
      "type": "string",
      "description": "Reason for failure"
    }
  }
}
```

### Example

```json
{
  "event_id": "01HYDLQ123456789ABCDEFGH",
  "aggregate_type": "Payment",
  "aggregate_id": "01HYDLQ123456789ABCDEFGH",
  "event_type": "PaymentAuthorized",
  "payload": {
    "payment_id": "01HYDLQ123456789ABCDEFGH",
    "payer_account_id": "01HY1234567890ABCDEFGHIJ",
    "payee_account_id": "01HY0987654321JIHGFEDCBA",
    "amount_cents": 5000,
    "currency": "USD"
  },
  "timestamp": "2024-01-15T10:30:00.123456+00:00",
  "retry_count": 5,
  "failed_at": "2024-01-15T10:45:00.123456+00:00",
  "error": "max_retries_exceeded"
}
```

---

## Consuming Events

### Sample Consumer (Python)

A sample consumer is provided in `scripts/sample_consumer.py`:

```python
#!/usr/bin/env python3
"""Sample event consumer for payment events."""
import asyncio
import json
from aiokafka import AIOKafkaConsumer

TOPICS = [
    "payments.paymentauthorized",
    "payments.paymentdeclined",
    "payments.dlq",
]

async def process_event(topic: str, event: dict) -> None:
    """Process a received event."""
    event_type = event.get("event_type", "unknown")
    payload = event.get("payload", {})

    if event_type == "PaymentAuthorized":
        # Send notification, update read model, trigger workflow, etc.
        print(f"Payment authorized: {payload['payment_id']}")
        print(f"  Amount: {payload['amount_cents']} {payload['currency']}")
        print(f"  From: {payload['payer_account_id']}")
        print(f"  To: {payload['payee_account_id']}")

async def consume_events() -> None:
    consumer = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers="localhost:19092",
        group_id="my-notification-service",
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    await consumer.start()
    try:
        async for msg in consumer:
            await process_event(msg.topic, msg.value)
    finally:
        await consumer.stop()

if __name__ == "__main__":
    asyncio.run(consume_events())
```

### Running the Consumer

```bash
# Using Makefile
make run-sample-consumer

# Or directly
PYTHONPATH=src uv run python scripts/sample_consumer.py
```

### Consumer Groups

The consumer uses a `group_id` for Kafka consumer group coordination:
- Multiple instances with the same `group_id` will share the load
- Each partition is consumed by only one consumer in the group
- Use unique `group_id` per service type (e.g., `notification-service`, `analytics-service`)

---

## Outbox Pattern Details

### Database Schema

The outbox table stores events until they are published:

```sql
CREATE TABLE outbox (
    id VARCHAR(26) PRIMARY KEY,              -- ULID
    aggregate_type VARCHAR(100) NOT NULL,    -- e.g., "Payment"
    aggregate_id VARCHAR(26) NOT NULL,       -- e.g., payment_id
    event_type VARCHAR(100) NOT NULL,        -- e.g., "PaymentAuthorized"
    payload JSONB NOT NULL,                  -- Event data
    created_at TIMESTAMPTZ NOT NULL,         -- When event was created
    published_at TIMESTAMPTZ,                -- NULL until published
    retry_count INTEGER NOT NULL DEFAULT 0   -- Retry attempts
);

-- Index for efficient polling of unpublished events
CREATE INDEX ix_outbox_unpublished ON outbox (created_at)
    WHERE published_at IS NULL;
```

### Retry Logic

The OutboxProcessor implements exponential backoff with jitter:

```
delay = min(base_delay * 2^retry_count, max_delay)
jitter = random(0, delay * 0.1)
actual_delay = delay + jitter
```

Default configuration:
- `base_delay`: 1.0 second
- `max_delay`: 60.0 seconds
- `max_retries`: 5

### Circuit Breaker

If the processor encounters 10 consecutive failures, it triggers a circuit breaker and stops processing. This prevents cascading failures when Kafka is unavailable.

---

## Configuration Reference

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `REDPANDA_BROKERS` | `localhost:19092` | Kafka/Redpanda broker addresses |
| `KAFKA_TOPIC_PREFIX` | `payments` | Prefix for topic names |
| `OUTBOX_BATCH_SIZE` | `100` | Max events per processing batch |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `1.0` | Seconds between polls |
| `OUTBOX_MAX_RETRIES` | `5` | Max retries before DLQ |
| `OUTBOX_BASE_DELAY_SECONDS` | `1.0` | Base delay for backoff |
| `OUTBOX_MAX_DELAY_SECONDS` | `60.0` | Maximum backoff delay |

---

## Monitoring

### Key Metrics to Track

1. **Outbox Queue Depth**: Count of events where `published_at IS NULL`
2. **Event Publishing Latency**: Time from `created_at` to `published_at`
3. **Retry Rate**: Events requiring multiple publish attempts
4. **DLQ Rate**: Events sent to dead letter queue

### Useful Queries

```sql
-- Count pending events
SELECT COUNT(*) FROM outbox WHERE published_at IS NULL;

-- Events by retry count
SELECT retry_count, COUNT(*)
FROM outbox
WHERE published_at IS NULL
GROUP BY retry_count;

-- Average publishing latency (last hour)
SELECT AVG(EXTRACT(EPOCH FROM (published_at - created_at))) as avg_latency_seconds
FROM outbox
WHERE published_at > NOW() - INTERVAL '1 hour';
```

---

## Best Practices

1. **Idempotent Consumers**: Always design consumers to handle duplicate events
2. **Event Ordering**: Events for the same `aggregate_id` are ordered; cross-aggregate ordering is not guaranteed
3. **Schema Evolution**: Add new optional fields; never remove or rename existing fields
4. **Consumer Lag Monitoring**: Monitor consumer group lag to detect processing issues
5. **DLQ Processing**: Regularly review and process DLQ events manually
