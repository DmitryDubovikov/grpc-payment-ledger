# Payment Flow — Step by Step

Visual guide showing the complete AuthorizePayment flow from gRPC request to database commit.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AuthorizePayment Flow                               │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   gRPC       │     │   Service    │     │   Domain     │     │   Database   │
│   Handler    │     │   Layer      │     │   Models     │     │   (Postgres) │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │                    │
```

---

## Phase 0: Request Reception

```
LOG: request_received method=AuthorizePayment idempotency_key=test-key-001
```

| File | Line | What Happens |
|------|------|--------------|
| `grpc_handlers.py` | 37-46 | `AuthorizePayment()` receives gRPC request |
| `grpc_handlers.py` | 48-70 | Validate required fields (idempotency_key, payer, payee, currency) |
| `grpc_handlers.py` | 72-74 | Create `UnitOfWork` and `PaymentService` |
| `grpc_handlers.py` | 76-83 | Build `AuthorizePaymentCommand` |
| `grpc_handlers.py` | 85 | Call `payment_service.authorize_payment(cmd)` |

**Objects involved:**
- `AuthorizePaymentRequest` (protobuf) → `AuthorizePaymentCommand` (dataclass)
- `UnitOfWork` — transaction boundary
- `PaymentService` — business logic orchestrator

---

## Phase 1: Idempotency Check

| File | Line | What Happens |
|------|------|--------------|
| `services.py` | 51-52 | `async with self.uow:` — start transaction |
| `services.py` | 52 | `idempotency.get(key)` — check if key exists |

**If key exists with status=COMPLETED:**
```
LOG: idempotent_replay payment_id=01JG...
```
| `services.py` | 53-59 | Return `DUPLICATE` status with cached payment_id |

**If key doesn't exist:**
| `services.py` | 61-65 | `idempotency.create(key, expires_at)` — create PENDING record |

---

## Step 1/4: Validation

```
LOG: payment_validated step=1/4 payer=acc-payer-001 payee=acc-payee-002 amount=5000
```

| File | Line | What Happens |
|------|------|--------------|
| `services.py` | 67 | Call `_validate_and_create_payment(cmd, log)` |
| `services.py` | 115-122 | Check `amount_cents > 0` |
| `services.py` | 124-129 | Check `payer_account_id != payee_account_id` |
| `services.py` | 131-139 | `accounts.get(payer_id)` — payer exists? |
| `services.py` | 141-149 | `accounts.get(payee_id)` — payee exists? |
| `services.py` | 151-165 | `balances.get(payer_id)` — sufficient funds? |
| `services.py` | 167-173 | **LOG** `payment_validated` |

**If validation fails:**
```
LOG: payment_declined reason=INSUFFICIENT_FUNDS available=95000 required=1000000
```
| `services.py` | 68-71 | `idempotency.mark_failed()`, `commit()`, return DECLINED |

**Objects involved:**
- `AccountRepository` — check account existence
- `BalanceRepository` — check available funds
- `AuthorizePaymentResult` — validation result

---

## Step 2/4: Transfer Preparation

```
LOG: payment_transferring step=2/4 payer_balance_before=100000 payee_balance_before=50000 amount=5000
```

| File | Line | What Happens |
|------|------|--------------|
| `services.py` | 73-79 | `Payment.create(...)` — generate ULID, set status=AUTHORIZED |
| `services.py` | 81 | `payments.add(payment)` — INSERT into payments table |
| `services.py` | 82 | Call `_execute_transfer(payment, log)` |
| `services.py` | 182 | `balances.get_for_update(payer_id)` — **SELECT FOR UPDATE** (lock row) |
| `services.py` | 183 | `balances.get_for_update(payee_id)` — **SELECT FOR UPDATE** (lock row) |
| `services.py` | 190-196 | Re-check balance after lock (race condition protection) |
| `services.py` | 198-199 | Calculate `new_payer_balance`, `new_payee_balance` |
| `services.py` | 201-207 | **LOG** `payment_transferring` |

**Objects involved:**
- `Payment` (domain model) — created with ULID
- `BalanceRepository.get_for_update()` — pessimistic locking
- `AccountBalance` — current balances

---

## Step 3/4: Ledger Entries

```
LOG: payment_ledger_created step=3/4 payer_balance_after=95000 payee_balance_after=55000
```

| File | Line | What Happens |
|------|------|--------------|
| `services.py` | 209-216 | `LedgerEntry.create(DEBIT, payer, amount, balance_after)` |
| `services.py` | 218-225 | `LedgerEntry.create(CREDIT, payee, amount, balance_after)` |
| `services.py` | 227-228 | `ledger.add(debit_entry)`, `ledger.add(credit_entry)` |
| `services.py` | 230-239 | `balances.update(payer_id, new_balance, version)` — optimistic lock |
| `services.py` | 241-246 | `balances.update(payee_id, new_balance, version)` — optimistic lock |
| `services.py` | 248-252 | **LOG** `payment_ledger_created` |

**Database operations:**
```sql
INSERT INTO ledger_entries (id, payment_id, account_id, entry_type, amount_cents, balance_after_cents, ...)
  VALUES ('...', '...', 'acc-payer-001', 'DEBIT', 5000, 95000, ...);

INSERT INTO ledger_entries (id, payment_id, account_id, entry_type, amount_cents, balance_after_cents, ...)
  VALUES ('...', '...', 'acc-payee-002', 'CREDIT', 5000, 55000, ...);

UPDATE account_balances SET available_balance_cents = 95000, version = version + 1
  WHERE account_id = 'acc-payer-001' AND version = 1;

UPDATE account_balances SET available_balance_cents = 55000, version = version + 1
  WHERE account_id = 'acc-payee-002' AND version = 1;
```

**Objects involved:**
- `LedgerEntry` (domain model) — double-entry bookkeeping
- `LedgerRepository` — INSERT ledger entries
- `BalanceRepository.update()` — UPDATE with optimistic locking

---

## Step 4/4: Completion

```
LOG: payment_completed step=4/4 payment_id=01JG... status=AUTHORIZED
```

| File | Line | What Happens |
|------|------|--------------|
| `services.py` | 84-95 | `outbox.add(PaymentAuthorized event)` — transactional outbox |
| `services.py` | 97-100 | `idempotency.mark_completed(key, payment_id)` |
| `services.py` | 102 | `commit()` — **COMMIT TRANSACTION** |
| `services.py` | 104 | **LOG** `payment_completed` |
| `services.py` | 106-110 | Return `AuthorizePaymentResult(AUTHORIZED)` |

**Database operations:**
```sql
INSERT INTO outbox (id, aggregate_type, aggregate_id, event_type, payload, ...)
  VALUES ('...', 'Payment', '01JG...', 'PaymentAuthorized', '{"payment_id": ...}', ...);

UPDATE idempotency_keys SET status = 'COMPLETED', payment_id = '01JG...'
  WHERE key = 'test-key-001';

COMMIT;
```

**Objects involved:**
- `OutboxRepository` — transactional outbox pattern
- `IdempotencyRepository` — mark as completed

---

## Response

| File | Line | What Happens |
|------|------|--------------|
| `grpc_handlers.py` | 87-102 | Build `AuthorizePaymentResponse` protobuf |
| `grpc_handlers.py` | 98-103 | Return response to client |

**Response:**
```json
{
  "paymentId": "01JG...",
  "status": "PAYMENT_STATUS_AUTHORIZED",
  "processedAt": "2025-12-31T13:12:54.478184"
}
```

---

## Summary: Files & Responsibilities

| File | Layer | Responsibility |
|------|-------|----------------|
| `grpc_handlers.py` | API | Request/response handling, field validation |
| `services.py` | Application | Business logic orchestration, transaction management |
| `models.py` | Domain | `Payment`, `LedgerEntry`, `AccountBalance` entities |
| `repositories/*.py` | Infrastructure | Database operations |
| `unit_of_work.py` | Infrastructure | Transaction boundary |

---

## Database Tables Modified

| Table | Operation | When |
|-------|-----------|------|
| `idempotency_keys` | INSERT | Phase 1 (if new key) |
| `payments` | INSERT | Step 2/4 |
| `ledger_entries` | INSERT x2 | Step 3/4 |
| `account_balances` | UPDATE x2 | Step 3/4 |
| `outbox` | INSERT | Step 4/4 |
| `idempotency_keys` | UPDATE | Step 4/4 |
