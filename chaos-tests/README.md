# Chaos Testing Scenarios

This directory contains chaos testing scenarios for the payment service.

## Prerequisites

- Docker Compose running all services
- k6 installed (for load testing during chaos)
- grpcurl installed (for health checks)

## Scenarios

### 1. Database Connection Loss

Test service behavior when PostgreSQL becomes unavailable.

```bash
# Start background load
k6 run --duration=5m load-tests/payment_load_test.js &

# Stop PostgreSQL
docker compose stop postgres

# Wait 30 seconds
sleep 30

# Check service health
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# Restart PostgreSQL
docker compose start postgres

# Wait for recovery
sleep 10

# Verify health recovered
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

**Expected Behavior:**
- Service should return gRPC UNAVAILABLE errors during outage
- Service should recover automatically when database returns
- No data corruption after recovery

### 2. Redis Connection Loss

Test rate limiting behavior when Redis is unavailable.

```bash
# Start background load
k6 run --duration=5m load-tests/payment_load_test.js &

# Stop Redis
docker compose stop redis

# Wait 30 seconds
sleep 30

# Verify payments still work (rate limiting may be degraded)
grpcurl -plaintext -d '{
  "idempotency_key": "chaos-test-001",
  "payer_account_id": "test-payer-001",
  "payee_account_id": "test-payee-001",
  "amount_cents": 100,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment

# Restart Redis
docker compose start redis

# Wait for recovery
sleep 10
```

**Expected Behavior:**
- Payments should continue to work (rate limiting degraded gracefully)
- Rate limiting should resume after Redis recovery
- No payment failures due to Redis outage

### 3. Redpanda Connection Loss

Test outbox processing when Kafka is unavailable.

```bash
# Stop Redpanda
docker compose stop redpanda

# Make several payments
for i in {1..10}; do
  grpcurl -plaintext -d "{
    \"idempotency_key\": \"chaos-redpanda-$i\",
    \"payer_account_id\": \"test-payer-001\",
    \"payee_account_id\": \"test-payee-001\",
    \"amount_cents\": 100,
    \"currency\": \"USD\"
  }" localhost:50051 payment.v1.PaymentService/AuthorizePayment
done

# Check outbox has pending events
docker compose exec postgres psql -U payment -d payment_db -c \
  "SELECT COUNT(*) FROM outbox WHERE published_at IS NULL;"

# Restart Redpanda
docker compose start redpanda

# Wait for outbox processor to catch up
sleep 30

# Verify all events published
docker compose exec postgres psql -U payment -d payment_db -c \
  "SELECT COUNT(*) FROM outbox WHERE published_at IS NULL;"
```

**Expected Behavior:**
- Payments should succeed even without Kafka
- Events accumulate in outbox table
- All events published after Kafka recovery
- No event loss

### 4. High Memory Pressure

Test service behavior under memory constraints.

```bash
# Update docker-compose to limit memory
# payment-service:
#   deploy:
#     resources:
#       limits:
#         memory: 256M

docker compose up -d payment-service

# Run load test
k6 run load-tests/payment_load_test.js

# Monitor memory usage
docker stats payment-service
```

**Expected Behavior:**
- Service should remain stable
- May slow down under pressure
- Should not crash or OOM
- Should recover when load decreases

### 5. Network Partition (Split Brain)

Simulate network issues between services.

```bash
# Using Docker network manipulation
# Disconnect payment service from postgres network
docker network disconnect grpc-payment-ledger_default payment-service

# Wait and observe
sleep 30

# Reconnect
docker network connect grpc-payment-ledger_default payment-service

# Verify recovery
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

**Expected Behavior:**
- Service should detect connection loss
- Should attempt reconnection
- Should recover automatically when network restored

### 6. Service Restart During Load

Test graceful shutdown under load.

```bash
# Start heavy load
k6 run --duration=5m --vus=100 load-tests/payment_load_test.js &

# Wait for load to stabilize
sleep 30

# Gracefully restart service
docker compose restart payment-service

# Monitor logs
docker compose logs -f payment-service
```

**Expected Behavior:**
- In-flight requests complete or timeout gracefully
- No data corruption
- Service restarts cleanly
- New requests handled after restart

## Monitoring During Chaos Tests

### Check Prometheus Metrics

```bash
# During tests, monitor metrics at:
curl http://localhost:9090/metrics | grep -E "(payment_|grpc_|rate_limit)"
```

### Check Logs

```bash
docker compose logs -f payment-service
```

### Check Database State

```bash
docker compose exec postgres psql -U payment -d payment_db -c "
  SELECT
    (SELECT COUNT(*) FROM payments) as payments,
    (SELECT COUNT(*) FROM ledger_entries) as ledger_entries,
    (SELECT SUM(available_balance_cents) FROM account_balances) as total_balance,
    (SELECT COUNT(*) FROM outbox WHERE published_at IS NULL) as pending_events;
"
```

## Success Criteria

1. **No Data Loss**: All committed payments survive chaos events
2. **Ledger Consistency**: Debits and credits always balance
3. **Graceful Degradation**: Service handles failures gracefully
4. **Recovery**: Service automatically recovers after failures
5. **Observability**: Failures are visible in logs and metrics
