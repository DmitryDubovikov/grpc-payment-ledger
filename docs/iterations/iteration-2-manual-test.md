# Manual Testing — Iteration 2

**Date**: 2025-12-31
**Focus**: Outbox Pattern & Event Publishing

## Environment Setup

### 1. Start the Project

```bash
# Navigate to project directory
cd grpc-payment-ledger

# Start all services (includes outbox-processor)
docker compose up -d

# Run migrations
make migrate

# Initialize test data
make init-test-data

# Verify everything is running
docker compose ps
```

**Expected Result:**
- All containers in `running` status:
  - `postgres` - PostgreSQL database
  - `redis` - Redis cache
  - `redpanda` - Kafka-compatible message broker
  - `redpanda-console` - Web UI for Redpanda
  - `payment-service` - gRPC server
  - `outbox-processor` - Event publisher worker

### 2. Verify Infrastructure

```bash
# Check PostgreSQL connection
docker compose exec postgres psql -U payment -d payment_db -c "\dt"

# Check Redis
docker compose exec redis redis-cli ping

# Check Redpanda
docker compose exec redpanda rpk cluster health

# Check Redpanda Console (open in browser)
open http://localhost:8080
```

---

## Test Cases

### TC-001: Payment Creates Outbox Event

**Description**: Verify that authorizing a payment creates an outbox event in the database.

**Preconditions**:
- Services running
- Test data initialized

**Steps**:

1. Make a payment authorization request:
```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "manual-test-001",
  "payer_account_id": "01HTEST0000000000000PAYER",
  "payee_account_id": "01HTEST0000000000000PAYEE",
  "amount_cents": 5000,
  "currency": "USD",
  "description": "Manual test payment"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

2. Check outbox table for the event:
```bash
docker compose exec postgres psql -U payment -d payment_db -c \
  "SELECT id, event_type, aggregate_id, published_at, retry_count FROM outbox ORDER BY created_at DESC LIMIT 5;"
```

**Expected Result**:
- [x] gRPC returns `PAYMENT_STATUS_AUTHORIZED`
- [x] Outbox table contains `PaymentAuthorized` event
- [x] `published_at` is NULL initially (or quickly becomes non-NULL if processor is running)

---

### TC-002: Outbox Processor Publishes Events

**Description**: Verify that the outbox processor picks up events and publishes them to Kafka.

**Steps**:

1. Check Kafka topics exist:
```bash
docker compose exec redpanda rpk topic list
```

2. If topics don't exist, create them:
```bash
docker compose exec redpanda rpk topic create payments.paymentauthorized payments.paymentdeclined payments.dlq --partitions 3
```

3. Start consuming events (in a separate terminal):
```bash
docker compose exec redpanda rpk topic consume payments.paymentauthorized --format json
```

4. Make a new payment:
```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "manual-test-002",
  "payer_account_id": "01HTEST0000000000000PAYER",
  "payee_account_id": "01HTEST0000000000000PAYEE",
  "amount_cents": 3000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected Result**:
- [x] Event appears in the consumer terminal
- [x] Event contains `event_id`, `aggregate_type`, `event_type`, `payload`, `timestamp`
- [x] Outbox table shows `published_at` is set

---

### TC-003: Event Schema Validation

**Description**: Verify published events match the JSON schema.

**Steps**:

1. Consume an event and save it to a file:
```bash
docker compose exec redpanda rpk topic consume payments.paymentauthorized --num 1 --format json > /tmp/event.json
```

2. Validate against schema (manually check structure):
```json
{
  "event_id": "01H...",                    // ULID format
  "aggregate_type": "Payment",             // Must be "Payment"
  "aggregate_id": "01H...",                // ULID format
  "event_type": "PaymentAuthorized",       // Event type
  "payload": {
    "payment_id": "01H...",
    "payer_account_id": "...",
    "payee_account_id": "...",
    "amount_cents": 5000,
    "currency": "USD"
  },
  "timestamp": "2024-01-15T10:30:00Z"      // ISO 8601
}
```

**Expected Result**:
- [x] Event structure matches schema
- [x] All required fields present
- [x] ULID format for IDs
- [x] ISO 4217 currency code

---

### TC-004: Declined Payment Event

**Description**: Verify declined payments generate `PaymentDeclined` events.

**Steps**:

1. Start consuming declined events:
```bash
docker compose exec redpanda rpk topic consume payments.paymentdeclined --format json
```

2. Make a payment with insufficient funds (if balance is low) or same account:
```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "manual-test-003",
  "payer_account_id": "01HTEST0000000000000PAYER",
  "payee_account_id": "01HTEST0000000000000PAYER",
  "amount_cents": 1000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected Result**:
- [x] gRPC returns `PAYMENT_STATUS_DECLINED` with `error_code: SAME_ACCOUNT`
- [x] `PaymentDeclined` event published to `payments.paymentdeclined` topic
- [x] Event payload contains `error_code` and `error_message`

---

### TC-005: Sample Consumer

**Description**: Verify the sample consumer processes events correctly.

**Steps**:

1. Run the sample consumer locally:
```bash
make run-sample-consumer
```

2. In another terminal, make a payment:
```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "manual-test-004",
  "payer_account_id": "01HTEST0000000000000PAYER",
  "payee_account_id": "01HTEST0000000000000PAYEE",
  "amount_cents": 2000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected Result**:
- [x] Consumer logs show `payment_authorized_event`
- [x] Log contains `payment_id`, `payer`, `payee`, `amount_cents`, `currency`

---

### TC-006: Outbox Processor Logs

**Description**: Verify outbox processor logs event publishing.

**Steps**:

1. View outbox processor logs:
```bash
make outbox-logs
```

2. Make a payment and observe logs.

**Expected Result**:
- [x] Logs show `event_published` with event details
- [x] Logs show `batch_published` with count

---

### TC-007: Retry Logic (Simulated)

**Description**: Verify retry count increments on publish failure.

*Note: This is difficult to test manually without stopping Redpanda. The test suite covers this.*

**Verification Query**:
```bash
docker compose exec postgres psql -U payment -d payment_db -c \
  "SELECT id, event_type, retry_count, published_at FROM outbox WHERE retry_count > 0;"
```

---

## gRPC Tests (grpcurl)

### Test GRPC-001: AuthorizePayment

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "grpc-test-001",
  "payer_account_id": "01HTEST0000000000000PAYER",
  "payee_account_id": "01HTEST0000000000000PAYEE",
  "amount_cents": 1000,
  "currency": "USD",
  "description": "gRPC test payment"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected Response:**
```json
{
  "paymentId": "01HXXX...",
  "status": "PAYMENT_STATUS_AUTHORIZED",
  "processedAt": "2025-12-31T..."
}
```

### Test GRPC-002: GetAccountBalance

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "account_id": "01HTEST0000000000000PAYER"
}' localhost:50051 payment.v1.PaymentService/GetAccountBalance
```

**Expected Response:**
```json
{
  "accountId": "01HTEST0000000000000PAYER",
  "availableBalanceCents": "...",
  "pendingBalanceCents": "0",
  "currency": "USD"
}
```

### Test GRPC-003: Health Check

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

**Expected Response:**
```json
{
  "status": "SERVING"
}
```

---

## Kafka/Redpanda Verification

### List Topics

```bash
make kafka-topics
# or
docker compose exec redpanda rpk topic list
```

### Consume Events

```bash
# PaymentAuthorized events
make kafka-consume

# Dead Letter Queue
make kafka-consume-dlq
```

### Check Outbox Table

```bash
docker compose exec postgres psql -U payment -d payment_db -c \
  "SELECT
    id,
    event_type,
    aggregate_id,
    published_at IS NOT NULL as is_published,
    retry_count
   FROM outbox
   ORDER BY created_at DESC
   LIMIT 10;"
```

---

## Completion Checklist

- [ ] All containers running
- [ ] Migrations applied successfully
- [ ] TC-001: Payment creates outbox event
- [ ] TC-002: Outbox processor publishes events
- [ ] TC-003: Event schema validated
- [ ] TC-004: Declined payment event
- [ ] TC-005: Sample consumer works
- [ ] TC-006: Outbox processor logs correctly
- [ ] GRPC-001: AuthorizePayment works
- [ ] GRPC-002: GetAccountBalance works
- [ ] GRPC-003: Health check returns SERVING
- [ ] Events appear in Redpanda Console (http://localhost:8080)

---

## Known Issues

| Issue | Workaround |
|-------|------------|
| Topics don't exist initially | Run `make kafka-create-topics` |
| Outbox processor not running | Check `docker compose ps`, restart with `docker compose restart outbox-processor` |

---

## Troubleshooting

**Problem**: PostgreSQL not starting
**Solution**: `docker compose down -v && docker compose up -d postgres`

**Problem**: Redpanda connection refused
**Solution**: Wait for health check, verify with `docker compose exec redpanda rpk cluster health`

**Problem**: No events appearing in consumer
**Solution**:
1. Check outbox processor logs: `make outbox-logs`
2. Check if events are in outbox table with `published_at IS NULL`
3. Verify topics exist: `make kafka-topics`

**Problem**: gRPC connection refused
**Solution**: Verify payment-service is running: `docker compose logs payment-service`
