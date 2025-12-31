# Detailed Testing Guide — Iteration 1

This guide provides step-by-step testing with detailed explanations of what happens inside the system.

## Prerequisites

```bash
make dev-up
make migrate
make reset-test-data
```

## How to Watch Logs

Run this in a separate terminal before executing tests:

```bash
docker compose logs -f payment-service
```

---

## Test 4: AuthorizePayment — Success

**Goal:** Verify complete successful payment flow

### Command

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

### Expected Response

```json
{
  "paymentId": "01JG...",
  "status": "PAYMENT_STATUS_AUTHORIZED",
  "processedAt": "2025-12-30T12:00:00.000000"
}
```

### Expected Logs (5 lines)

```
request_received     method=AuthorizePayment idempotency_key=test-key-001
payment_validated    step=1/4 payer=acc-payer-001 payee=acc-payee-002 amount=5000
payment_transferring step=2/4 payer_balance_before=100000 payee_balance_before=50000 amount=5000
payment_ledger_created step=3/4 payer_balance_after=95000 payee_balance_after=55000
payment_completed    step=4/4 payment_id=01JG... status=AUTHORIZED
```

Note: `request_received` is logged by gRPC handler layer. Steps 1-4 are from payment service.

### What Happens Inside

| Step | Action | Details |
|------|--------|---------|
| 1/4 | Validation | Check amount > 0, payer ≠ payee, both accounts exist, sufficient funds |
| 2/4 | Transfer Start | Lock balances with `SELECT FOR UPDATE`, calculate new values |
| 3/4 | Ledger Created | Create DEBIT entry (payer) and CREDIT entry (payee) |
| 4/4 | Completed | Save to outbox, mark idempotency key completed, commit |

### Database Verification

```sql
-- Check payment created
SELECT id, status, amount_cents FROM payments
WHERE idempotency_key = 'test-key-001';

-- Check balances changed
SELECT account_id, available_balance_cents, version
FROM account_balances
WHERE account_id IN ('acc-payer-001', 'acc-payee-002');
-- Expected: payer=95000, payee=55000, both versions incremented

-- Check ledger entries (double-entry bookkeeping)
SELECT account_id, entry_type, amount_cents, balance_after_cents
FROM ledger_entries
WHERE payment_id = '<payment_id>';
-- Expected: 2 rows (DEBIT + CREDIT), same amount
```

---

## Test 5: Idempotency — Duplicate Request

**Goal:** Verify duplicate request returns same result without reprocessing

### Command

Send the exact same request as Test 4:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-001",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 5000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

### Expected Response

```json
{
  "paymentId": "01JG...",
  "status": "PAYMENT_STATUS_DUPLICATE",
  "processedAt": "2025-12-30T12:00:00.000000"
}
```

Note: Same `paymentId` as Test 4, status is `DUPLICATE`.

### Expected Logs (1 log)

```
idempotent_replay payment_id=01JG...
```

### What Happens Inside

1. Check idempotency key → **FOUND with status=COMPLETED**
2. Return immediately with `status=DUPLICATE` and original `payment_id`
3. **NO database operations** (no balance changes, no new ledger entries)

### Database Verification

```sql
-- Count payments (should be same as after Test 4)
SELECT COUNT(*) FROM payments;

-- Balances unchanged
SELECT available_balance_cents FROM account_balances
WHERE account_id = 'acc-payer-001';
-- Expected: still 95000
```

---

## Test 6: GetPayment

**Goal:** Retrieve payment details

### Command

Replace `<PAYMENT_ID>` with the actual payment_id from Test 4:

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "payment_id": "<PAYMENT_ID>"
}' localhost:50051 payment.v1.PaymentService/GetPayment
```

### Expected Response

```json
{
  "payment": {
    "paymentId": "01JG...",
    "payerAccountId": "acc-payer-001",
    "payeeAccountId": "acc-payee-002",
    "amountCents": "5000",
    "currency": "USD",
    "status": "PAYMENT_STATUS_AUTHORIZED",
    "description": "Test payment",
    "createdAt": "...",
    "updatedAt": "..."
  }
}
```

### Expected Logs (1 log)

```
get_payment payment_id=01JG... status=AUTHORIZED amount=5000
```

### What Happens Inside

Simple `SELECT` from payments table. Returns all payment fields.

---

## Test 7: GetAccountBalance

**Goal:** Verify API returns correct balances after payment

### Command (Payer)

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "account_id": "acc-payer-001"
}' localhost:50051 payment.v1.PaymentService/GetAccountBalance
```

### Expected Response (Payer)

```json
{
  "accountId": "acc-payer-001",
  "availableBalanceCents": "95000",
  "pendingBalanceCents": "0",
  "currency": "USD"
}
```

Note: Balance reduced from 100000 to 95000 ($950).

### Command (Payee)

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "account_id": "acc-payee-002"
}' localhost:50051 payment.v1.PaymentService/GetAccountBalance
```

### Expected Response (Payee)

```json
{
  "accountId": "acc-payee-002",
  "availableBalanceCents": "55000",
  "pendingBalanceCents": "0",
  "currency": "USD"
}
```

Note: Balance increased from 50000 to 55000 ($550).

### Expected Logs (1 log per call)

```
get_balance account_id=acc-payer-001 available=95000
get_balance account_id=acc-payee-002 available=55000
```

### Database Verification

```sql
-- Compare API response with database
SELECT * FROM account_balances WHERE account_id = 'acc-payer-001';
```

---

## Test 8: Insufficient Funds

**Goal:** Verify payment is declined when balance is too low

### Command

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "test-key-002",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 1000000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

### Expected Response

```json
{
  "paymentId": "",
  "status": "PAYMENT_STATUS_DECLINED",
  "error": {
    "code": "PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS",
    "message": "Insufficient funds"
  },
  "processedAt": "..."
}
```

Note: `paymentId` is empty because payment was not created.

### Expected Logs (1 log)

```
payment_declined reason=INSUFFICIENT_FUNDS available=95000 required=1000000
```

### What Happens Inside

| Step | Action | Result |
|------|--------|--------|
| 1 | Check idempotency | Not found → create with status=PENDING |
| 2 | Validate amount | OK (> 0) |
| 3 | Validate accounts | OK (different, both exist) |
| 4 | Check balance | **FAIL** (95000 < 1000000) |
| 5 | Return DECLINED | Mark idempotency as FAILED, commit |

### What Does NOT Happen

- Payment record is **NOT created** (empty payment_id in response)
- Ledger entries are **NOT created**
- Balances are **NOT modified**
- Outbox event is **NOT created**

### Database Verification

```sql
-- Balances unchanged
SELECT available_balance_cents FROM account_balances
WHERE account_id = 'acc-payer-001';
-- Expected: still 95000

-- No payment for this key
SELECT * FROM payments WHERE idempotency_key = 'test-key-002';
-- Expected: empty

-- Idempotency marked as failed
SELECT status FROM idempotency_keys WHERE key = 'test-key-002';
-- Expected: FAILED
```

---

## Test 14: Verify Ledger Entries

**Goal:** Audit double-entry bookkeeping integrity

### Command

Connect to database:

```bash
docker compose exec postgres psql -U payment -d payment_db
```

### Integrity Checks

```sql
-- 1. Every payment has exactly 2 entries
SELECT payment_id, COUNT(*) as cnt
FROM ledger_entries
GROUP BY payment_id
HAVING COUNT(*) != 2;
-- Expected: empty (all payments have 2 entries)

-- 2. DEBIT = CREDIT for every payment
SELECT payment_id,
  SUM(CASE WHEN entry_type = 'DEBIT' THEN amount_cents ELSE 0 END) as debits,
  SUM(CASE WHEN entry_type = 'CREDIT' THEN amount_cents ELSE 0 END) as credits
FROM ledger_entries
GROUP BY payment_id
HAVING SUM(CASE WHEN entry_type = 'DEBIT' THEN amount_cents ELSE 0 END)
    != SUM(CASE WHEN entry_type = 'CREDIT' THEN amount_cents ELSE 0 END);
-- Expected: empty (debits = credits)

-- 3. All successful payments have outbox events
SELECT p.id, p.status
FROM payments p
LEFT JOIN outbox o ON p.id = o.aggregate_id
WHERE p.status = 'AUTHORIZED' AND o.id IS NULL;
-- Expected: empty (all AUTHORIZED have events)
```

---

## Troubleshooting

### No logs appearing

```bash
# Check service is running
docker compose ps

# Check log level
docker compose exec payment-service printenv | grep LOG
```

### Logs not structured

Check `LOG_FORMAT` env variable. Should be `json` for structured output or unset for human-readable.
