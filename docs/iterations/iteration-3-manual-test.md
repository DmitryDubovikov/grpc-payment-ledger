# Manual Testing - Iteration 3

**Date**: 2025-12-31
**Version**: 7ee1ba9

## Environment Setup

### 1. Start the Project

```bash
# Clone (if needed)
git clone <repo>
cd grpc-payment-ledger

# Start all services
docker compose up -d

# Run migrations
make migrate

# Verify everything is running
docker compose ps
```

**Expected Result:**
- All containers in `running` status
- PostgreSQL available: localhost:5432
- Redis available: localhost:6379
- Redpanda available: localhost:19092
- gRPC server: localhost:50051
- Metrics server: localhost:9090

### 2. Verify Infrastructure

```bash
# Check PostgreSQL connection
docker compose exec postgres psql -U payment -d payment_db -c "\dt"

# Check Redis
docker compose exec redis redis-cli ping

# Check Redpanda
docker compose exec redpanda rpk cluster health
```

---

## gRPC Tests (grpcurl via Docker)

All `grpcurl` commands run via Docker — no local installation needed.

### Helper Alias (Optional)

Add this alias to simplify commands:

```bash
alias grpcurl='docker run --rm --network=host fullstorydev/grpcurl'
```

Or use the full Docker command for each test.

### Test GRPC-001: Health Check

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

**Expected response:**
```json
{
  "status": "SERVING"
}
```

### Test GRPC-002: Payment Service Health

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{"service": "payment.v1.PaymentService"}' \
  localhost:50051 grpc.health.v1.Health/Check
```

**Expected response:**
```json
{
  "status": "SERVING"
}
```

### Test GRPC-003: List Services (Reflection)

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 list
```

**Expected response:**
```
grpc.health.v1.Health
grpc.reflection.v1alpha.ServerReflection
payment.v1.PaymentService
```

### Test GRPC-004: Describe Payment Service

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 describe payment.v1.PaymentService
```

**Expected:** Service description with all RPC methods.

### Test GRPC-005: AuthorizePayment

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-001",
  "payer_account_id": "test-payer-001",
  "payee_account_id": "test-payee-001",
  "amount_cents": 1000,
  "currency": "USD",
  "description": "Test payment"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected response:**
```json
{
  "paymentId": "01HXXX...",
  "status": "PAYMENT_STATUS_AUTHORIZED",
  "processedAt": "2024-01-15T10:30:00Z"
}
```

### Test GRPC-006: GetAccountBalance

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{"account_id": "test-payer-001"}' \
  localhost:50051 payment.v1.PaymentService/GetAccountBalance
```

**Expected response:**
```json
{
  "accountId": "test-payer-001",
  "availableBalanceCents": "...",
  "pendingBalanceCents": "0",
  "currency": "USD"
}
```

---

## Metrics Tests

### Test METRICS-001: Metrics Endpoint Available

```bash
curl -s http://localhost:9090/metrics | head -20
```

**Expected:** Prometheus metrics in text format.

### Test METRICS-002: Payment Metrics Present

```bash
curl -s http://localhost:9090/metrics | grep -E "^(payment_|grpc_|rate_limit)"
```

**Expected metrics:**
- `payment_requests_total`
- `payment_duration_seconds`
- `grpc_requests_total`
- `grpc_request_duration_seconds`
- `rate_limit_exceeded_total`

### Test METRICS-003: Metrics Health Endpoint

```bash
curl -s http://localhost:9090/health
```

**Expected response:**
```json
{"status": "healthy"}
```

---

## Rate Limiting Tests

### Test RATELIMIT-001: Normal Request (Under Limit)

Make several requests and verify they all succeed:

```bash
for i in {1..5}; do
  docker run --rm --network=host fullstorydev/grpcurl -plaintext -d "{
    \"idempotency_key\": \"rate-test-$i\",
    \"payer_account_id\": \"test-payer-001\",
    \"payee_account_id\": \"test-payee-001\",
    \"amount_cents\": 100,
    \"currency\": \"USD\"
  }" localhost:50051 payment.v1.PaymentService/AuthorizePayment
  echo "---"
done
```

**Expected:** All requests succeed with AUTHORIZED or DECLINED status.

### Test RATELIMIT-002: Rate Limit Counter

```bash
curl -s http://localhost:9090/metrics | grep rate_limit_exceeded_total
```

**Expected:** Counter shows number of rate-limited requests.

---

## Load Testing

Load tests run via Docker (k6) — no local installation needed.

**Note:** Before running load tests, reset test data to ensure sufficient balance:
```bash
make reset-test-data
```

### Test LOAD-001: Smoke Test

```bash
make load-test-smoke
```

**Expected:**
- All checks pass (rate > 95%)
- p(95) latency < 500ms
- No errors
- Summary shows authorized and declined counts

### Test LOAD-002: Full Load Test

```bash
make load-test
```

**Expected:**
- Summary shows authorized, declined, and duplicate counts
- No timeouts or connection errors
- Metrics show increased request counts

---

## Completion Checklist

- [ ] All containers running
- [ ] Migrations applied successfully
- [ ] Health check returns SERVING
- [ ] Reflection lists all services
- [ ] Metrics endpoint accessible
- [ ] Payment authorization works
- [ ] Balance check works
- [ ] Rate limiting metrics visible
- [ ] Load test passes
- [ ] No errors in logs

---

## Troubleshooting

**Problem**: gRPC connection refused
**Solution**: Verify server is running: `docker compose logs payment-service`

**Problem**: Metrics endpoint not accessible
**Solution**: Check port 9090 is exposed: `docker compose ps`

**Problem**: Rate limiting not working
**Solution**: Check Redis connection: `docker compose logs payment-service | grep redis`

**Problem**: Health check returns NOT_SERVING
**Solution**: Check all dependencies: `docker compose ps`

---

## Log Monitoring

```bash
# gRPC server logs
docker compose logs -f payment-service

# Check for rate limiting events
docker compose logs payment-service | grep rate_limit

# Check for errors
docker compose logs payment-service | grep -i error
```
