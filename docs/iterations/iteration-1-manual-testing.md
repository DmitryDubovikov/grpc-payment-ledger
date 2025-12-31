# Manual Testing Guide — Iteration 1

This guide walks through testing the Payment Service manually using `grpcurl` via Docker (no local installation required).

## Prerequisites

1. Start the services:
   ```bash
   make dev-up
   make migrate
   make reset-test-data
   ```

   **Note:** `reset-test-data` clears all existing data and re-creates test accounts. Use `init-test-data` if you only want to add accounts without clearing.

2. All `grpcurl` commands run via Docker — no local installation needed.

## Helper Alias (Optional)

Add this alias to simplify commands:

```bash
alias grpcurl='docker run --rm --network=host fullstorydev/grpcurl'
```

Or use the full Docker command for each test.

## Test 1: Service Discovery

Verify gRPC reflection is working:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 list
```

**Expected output:**
```
grpc.health.v1.Health
grpc.reflection.v1.ServerReflection
grpc.reflection.v1alpha.ServerReflection
payment.v1.PaymentService
```

## Test 2: Health Check

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

**Expected output:**
```json
{
  "status": "SERVING"
}
```

## Test 3: Setup Test Accounts

Test accounts are automatically created by `make reset-test-data` in Prerequisites.

If you need to reset test data (clear all and start fresh):

```bash
make reset-test-data
```

To verify accounts were created:

```bash
docker compose exec postgres psql -U payment -d payment_db -c "SELECT * FROM accounts; SELECT * FROM account_balances;"
```

## Test 4: AuthorizePayment — Success

Transfer $50 from payer to payee:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-001",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 5000,
  "currency": "USD",
  "description": "Test payment"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected output:**
```json
{
  "paymentId": "01JGXXXXXXXXXXXXXXXXXX",
  "status": "PAYMENT_STATUS_AUTHORIZED",
  "processedAt": "2025-12-30T12:00:00.000000"
}
```

## Test 5: Idempotency — Duplicate Request

Send the same request again (same idempotency_key):

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-001",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 5000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected output:**
```json
{
  "paymentId": "01JGXXXXXXXXXXXXXXXXXX",
  "status": "PAYMENT_STATUS_DUPLICATE",
  "processedAt": "2025-12-30T12:00:00.000000"
}
```

Note: Same payment_id returned, status is DUPLICATE.

## Test 6: GetPayment

Retrieve the payment created in Test 4:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "payment_id": "01JGXXXXXXXXXXXXXXXXXX"
}' localhost:50051 payment.v1.PaymentService/GetPayment
```

Replace `01JGXXXXXXXXXXXXXXXXXX` with the actual payment_id from Test 4.

**Expected output:**
```json
{
  "payment": {
    "paymentId": "01JGXXXXXXXXXXXXXXXXXX",
    "payerAccountId": "acc-payer-001",
    "payeeAccountId": "acc-payee-002",
    "amountCents": "5000",
    "currency": "USD",
    "status": "PAYMENT_STATUS_AUTHORIZED",
    "description": "Test payment",
    "createdAt": "2025-12-30T12:00:00.000000",
    "updatedAt": "2025-12-30T12:00:00.000000"
  }
}
```

## Test 7: GetAccountBalance

Check payer's balance after payment:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "account_id": "acc-payer-001"
}' localhost:50051 payment.v1.PaymentService/GetAccountBalance
```

**Expected output:**
```json
{
  "accountId": "acc-payer-001",
  "availableBalanceCents": "95000",
  "pendingBalanceCents": "0",
  "currency": "USD"
}
```

Note: Balance reduced from 100000 to 95000 ($950).

Check payee's balance:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "account_id": "acc-payee-002"
}' localhost:50051 payment.v1.PaymentService/GetAccountBalance
```

**Expected output:**
```json
{
  "accountId": "acc-payee-002",
  "availableBalanceCents": "55000",
  "pendingBalanceCents": "0",
  "currency": "USD"
}
```

Note: Balance increased from 50000 to 55000 ($550).

## Test 8: Validation — Insufficient Funds

Try to transfer more than available:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-002",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 1000000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected output:**
```json
{
  "paymentId": "01JGXXXXXXXXXXXXXXXXXX",
  "status": "PAYMENT_STATUS_DECLINED",
  "error": {
    "code": "PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS",
    "message": "Insufficient funds in account acc-payer-001"
  },
  "processedAt": "2025-12-30T12:00:00.000000"
}
```

## Test 9: Validation — Same Account

Try to pay yourself:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-003",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payer-001",
  "amount_cents": 1000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected output:**
```json
{
  "paymentId": "01JGXXXXXXXXXXXXXXXXXX",
  "status": "PAYMENT_STATUS_DECLINED",
  "error": {
    "code": "PAYMENT_ERROR_CODE_SAME_ACCOUNT",
    "message": "Payer and payee accounts must be different"
  },
  "processedAt": "2025-12-30T12:00:00.000000"
}
```

## Test 10: Validation — Invalid Amount

Try zero amount:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-004",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 0,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected output:**
```json
{
  "paymentId": "01JGXXXXXXXXXXXXXXXXXX",
  "status": "PAYMENT_STATUS_DECLINED",
  "error": {
    "code": "PAYMENT_ERROR_CODE_INVALID_AMOUNT",
    "message": "Amount must be greater than 0"
  },
  "processedAt": "2025-12-30T12:00:00.000000"
}
```

## Test 11: Validation — Account Not Found

Try non-existent account:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-005",
  "payer_account_id": "non-existent-account",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 1000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected output:**
```json
{
  "paymentId": "01JGXXXXXXXXXXXXXXXXXX",
  "status": "PAYMENT_STATUS_DECLINED",
  "error": {
    "code": "PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND",
    "message": "Payer account not found: non-existent-account"
  },
  "processedAt": "2025-12-30T12:00:00.000000"
}
```

## Test 12: Validation — Missing Required Field

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 1000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Expected output:**
```
ERROR:
  Code: InvalidArgument
  Message: idempotency_key is required
```

## Test 13: GetPayment — Not Found

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "payment_id": "non-existent-payment"
}' localhost:50051 payment.v1.PaymentService/GetPayment
```

**Expected output:**
```
ERROR:
  Code: NotFound
  Message: Payment non-existent-payment not found
```

## Test 14: Verify Ledger Entries

Check the database for ledger entries:

```bash
docker compose exec postgres psql -U payment -d payment_db
```

```sql
SELECT
  id,
  payment_id,
  account_id,
  entry_type,
  amount_cents,
  balance_after_cents,
  created_at
FROM ledger_entries
ORDER BY created_at;
```

**Expected:** Two entries per successful payment (DEBIT for payer, CREDIT for payee).

```sql
SELECT * FROM idempotency_keys;
```

**Expected:** Records for all idempotency keys used.

```sql
SELECT * FROM outbox;
```

**Expected:** Events for successful payments (ready for publishing to Redpanda).

Exit psql: `\q`

## Cleanup

To reset the test environment:

```bash
make dev-down
docker volume rm grpc-payment-ledger_postgres_data
make dev-up
make migrate
```

## Troubleshooting

### Service not responding

```bash
# Check if service is running
docker compose ps

# Check logs
docker compose logs payment-service

# Verify port is listening
docker compose exec payment-service python -c "import grpc; ch = grpc.insecure_channel('localhost:50051'); grpc.channel_ready_future(ch).result(timeout=5); print('OK')"
```

### Database connection issues

```bash
# Check PostgreSQL
docker compose logs postgres

# Verify connection
docker compose exec postgres pg_isready
```

### gRPC reflection not working

```bash
# Ensure GRPC_REFLECTION_ENABLED=true in .env
cat .env | grep GRPC_REFLECTION

# Restart service
docker compose restart payment-service
```
