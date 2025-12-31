# Database Schema

## Overview

PostgreSQL database with double-entry ledger accounting. All tables use ULID (Universally Unique Lexicographically Sortable Identifier) as primary keys for better indexing and sortability.

**Database**: PostgreSQL 16
**Driver**: asyncpg (async)
**ORM**: SQLAlchemy 2.0 (async)
**Migrations**: Alembic

---

## Tables

### accounts

Stores user accounts.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | VARCHAR(26) | NO | - | Primary key (ULID) |
| owner_id | VARCHAR(255) | NO | - | User/owner identifier |
| currency | VARCHAR(3) | NO | 'USD' | ISO 4217 currency code |
| status | VARCHAR(20) | NO | 'ACTIVE' | Account status |
| created_at | TIMESTAMPTZ | NO | now() | Creation timestamp |
| updated_at | TIMESTAMPTZ | NO | now() | Last update timestamp |

**Status Values:**
- `ACTIVE` - Account is operational
- `SUSPENDED` - Account is temporarily disabled
- `CLOSED` - Account is permanently closed

**Indexes:**
| Index Name | Columns | Type | Description |
|------------|---------|------|-------------|
| accounts_pkey | id | PRIMARY KEY | Primary key |
| ix_accounts_owner_id | owner_id | B-TREE | Lookup by owner |

---

### payments

Stores payment records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | VARCHAR(26) | NO | - | Primary key (ULID) |
| idempotency_key | VARCHAR(255) | NO | - | Unique idempotency key |
| payer_account_id | VARCHAR(26) | NO | - | FK to accounts (sender) |
| payee_account_id | VARCHAR(26) | NO | - | FK to accounts (recipient) |
| amount_cents | BIGINT | NO | - | Amount in smallest currency unit |
| currency | VARCHAR(3) | NO | - | ISO 4217 currency code |
| status | VARCHAR(20) | NO | - | Payment status |
| description | TEXT | YES | NULL | Payment memo |
| error_code | VARCHAR(50) | YES | NULL | Error code if declined |
| error_message | TEXT | YES | NULL | Error details if declined |
| created_at | TIMESTAMPTZ | NO | now() | Creation timestamp |
| updated_at | TIMESTAMPTZ | NO | now() | Last update timestamp |

**Status Values:**
- `AUTHORIZED` - Payment was successful
- `DECLINED` - Payment was rejected
- `DUPLICATE` - Idempotent replay

**Foreign Keys:**
| Column | References | On Delete |
|--------|------------|-----------|
| payer_account_id | accounts(id) | RESTRICT |
| payee_account_id | accounts(id) | RESTRICT |

**Indexes:**
| Index Name | Columns | Type | Description |
|------------|---------|------|-------------|
| payments_pkey | id | PRIMARY KEY | Primary key |
| ix_payments_idempotency_key | idempotency_key | UNIQUE | Idempotency lookup |
| ix_payments_payer_account_id | payer_account_id | B-TREE | Lookup by payer |
| ix_payments_payee_account_id | payee_account_id | B-TREE | Lookup by payee |
| ix_payments_created_at | created_at | B-TREE | Time-based queries |

---

### ledger_entries

Double-entry ledger (DEBIT and CREDIT entries). Every payment creates exactly two entries: a DEBIT for the payer and a CREDIT for the payee.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | VARCHAR(26) | NO | - | Primary key (ULID) |
| payment_id | VARCHAR(26) | NO | - | FK to payments |
| account_id | VARCHAR(26) | NO | - | FK to accounts |
| entry_type | VARCHAR(10) | NO | - | DEBIT or CREDIT |
| amount_cents | BIGINT | NO | - | Entry amount |
| currency | VARCHAR(3) | NO | - | ISO 4217 currency code |
| balance_after_cents | BIGINT | NO | - | Account balance after this entry |
| created_at | TIMESTAMPTZ | NO | now() | Creation timestamp |

**Entry Types:**
- `DEBIT` - Decreases account balance (money leaving)
- `CREDIT` - Increases account balance (money arriving)

**Accounting Invariant:**
For every payment, the sum of DEBIT entries must equal the sum of CREDIT entries.

**Foreign Keys:**
| Column | References | On Delete |
|--------|------------|-----------|
| payment_id | payments(id) | RESTRICT |
| account_id | accounts(id) | RESTRICT |

**Indexes:**
| Index Name | Columns | Type | Description |
|------------|---------|------|-------------|
| ledger_entries_pkey | id | PRIMARY KEY | Primary key |
| ix_ledger_entries_payment_id | payment_id | B-TREE | Lookup by payment |
| ix_ledger_entries_account_id | account_id | B-TREE | Account history |
| ix_ledger_entries_created_at | created_at | B-TREE | Time-based queries |

---

### account_balances

Denormalized balance for performance. Uses optimistic locking via version field.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| account_id | VARCHAR(26) | NO | - | Primary key, FK to accounts |
| available_balance_cents | BIGINT | NO | 0 | Available balance |
| pending_balance_cents | BIGINT | NO | 0 | Pending/reserved balance |
| currency | VARCHAR(3) | NO | - | ISO 4217 currency code |
| version | BIGINT | NO | 1 | Optimistic lock version |
| updated_at | TIMESTAMPTZ | NO | now() | Last update timestamp |

**Optimistic Locking:**
The `version` field is incremented on every update. Updates specify the expected version and fail if it doesn't match (concurrent modification detected).

**Foreign Keys:**
| Column | References | On Delete |
|--------|------------|-----------|
| account_id | accounts(id) | CASCADE |

**Indexes:**
| Index Name | Columns | Type | Description |
|------------|---------|------|-------------|
| account_balances_pkey | account_id | PRIMARY KEY | Primary key |

---

### idempotency_keys

Tracks idempotency keys for duplicate request detection.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| key | VARCHAR(255) | NO | - | Primary key (idempotency key) |
| payment_id | VARCHAR(26) | YES | NULL | FK to payments (if completed) |
| response_data | JSONB | YES | NULL | Cached response data |
| status | VARCHAR(20) | NO | 'PENDING' | Processing status |
| created_at | TIMESTAMPTZ | NO | now() | Creation timestamp |
| expires_at | TIMESTAMPTZ | NO | - | Expiration time (24h default) |

**Status Values:**
- `PENDING` - Request is being processed
- `COMPLETED` - Request completed successfully
- `FAILED` - Request failed

**Foreign Keys:**
| Column | References | On Delete |
|--------|------------|-----------|
| payment_id | payments(id) | SET NULL |

**Indexes:**
| Index Name | Columns | Type | Description |
|------------|---------|------|-------------|
| idempotency_keys_pkey | key | PRIMARY KEY | Primary key |
| ix_idempotency_keys_expires_at | expires_at | B-TREE | Cleanup expired keys |

---

### outbox

Transactional outbox for reliable event publishing. Events are written to this table within the same transaction as the business operation.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | VARCHAR(26) | NO | - | Primary key (ULID) |
| aggregate_type | VARCHAR(100) | NO | - | Entity type (e.g., "Payment") |
| aggregate_id | VARCHAR(26) | NO | - | Entity ID |
| event_type | VARCHAR(100) | NO | - | Event name (e.g., "PaymentAuthorized") |
| payload | JSONB | NO | - | Event data |
| created_at | TIMESTAMPTZ | NO | now() | Creation timestamp |
| published_at | TIMESTAMPTZ | YES | NULL | When published (NULL = pending) |
| retry_count | INTEGER | NO | 0 | Number of publish attempts |

**Event Types:**
- `PaymentAuthorized` - Payment was successfully authorized

**Payload Example:**
```json
{
  "payment_id": "01HYABCDEF1234567890QRST",
  "payer_account_id": "01HY1234567890ABCDEFGHIJ",
  "payee_account_id": "01HY0987654321JIHGFEDCBA",
  "amount_cents": 5000,
  "currency": "USD"
}
```

**Indexes:**
| Index Name | Columns | Type | Description |
|------------|---------|------|-------------|
| outbox_pkey | id | PRIMARY KEY | Primary key |
| ix_outbox_unpublished | created_at | PARTIAL | Pending events (WHERE published_at IS NULL) |
| ix_outbox_aggregate | (aggregate_type, aggregate_id) | B-TREE | Lookup by aggregate |

---

## Entity Relationship Diagram

```
┌─────────────────┐       ┌────────────────────┐       ┌───────────────────┐
│    accounts     │───┐   │      payments      │   ┌───│   ledger_entries  │
├─────────────────┤   │   ├────────────────────┤   │   ├───────────────────┤
│ id (PK)         │   └──→│ payer_account_id   │   │   │ id (PK)           │
│ owner_id        │       │ payee_account_id   │←──┘   │ payment_id (FK)   │
│ currency        │       │ idempotency_key    │       │ account_id (FK)   │
│ status          │       │ amount_cents       │       │ entry_type        │
│ created_at      │       │ currency           │       │ amount_cents      │
│ updated_at      │       │ status             │       │ currency          │
└────────┬────────┘       │ description        │       │ balance_after     │
         │                │ error_code         │       │ created_at        │
         │                │ error_message      │       └───────────────────┘
         │                │ created_at         │
         │                │ updated_at         │
         │                └─────────┬──────────┘
         │                          │
         ▼                          │
┌────────────────────┐              │
│  account_balances  │              │
├────────────────────┤              │
│ account_id (PK,FK) │              │
│ available_balance  │              │
│ pending_balance    │              │
│ currency           │              │
│ version            │              │
│ updated_at         │              │
└────────────────────┘              │
                                    │
┌────────────────────┐              │
│ idempotency_keys   │              │
├────────────────────┤              │
│ key (PK)           │◄─────────────┤
│ payment_id (FK)    │──────────────┘
│ response_data      │
│ status             │
│ created_at         │
│ expires_at         │
└────────────────────┘

┌────────────────────┐
│       outbox       │
├────────────────────┤
│ id (PK)            │
│ aggregate_type     │
│ aggregate_id       │
│ event_type         │
│ payload            │
│ created_at         │
│ published_at       │
│ retry_count        │
└────────────────────┘
```

---

## Migration History

| Revision | Description | Date |
|----------|-------------|------|
| 001 | Initial schema: accounts, payments, ledger, idempotency, outbox | 2024-01-01 |

---

## Data Integrity

### Double-Entry Accounting

Every payment creates exactly two ledger entries:
1. **DEBIT** entry for the payer (decreases balance)
2. **CREDIT** entry for the payee (increases balance)

The sum of all DEBIT entries for a payment equals the sum of all CREDIT entries.

### Optimistic Locking

Account balances use optimistic locking via the `version` field:
1. Read current balance and version
2. Calculate new balance
3. Update with `WHERE version = expected_version`
4. If rows affected = 0, concurrent modification detected (retry)

### Idempotency

The `idempotency_keys` table prevents duplicate payments:
1. Check if key exists
2. If exists and COMPLETED, return cached response
3. If not exists, create with PENDING status
4. Process payment
5. Mark as COMPLETED with payment_id

### Outbox Pattern

Events are written to the `outbox` table within the same transaction:
1. Begin transaction
2. Process payment
3. Write outbox event
4. Commit transaction
5. Background worker publishes events and sets `published_at`

This ensures events are only published if the transaction succeeds.

---

## Queries

### Get Account Balance

```sql
SELECT available_balance_cents, pending_balance_cents, currency, version
FROM account_balances
WHERE account_id = $1;
```

### Get Payment History for Account

```sql
SELECT p.*
FROM payments p
WHERE p.payer_account_id = $1 OR p.payee_account_id = $1
ORDER BY p.created_at DESC
LIMIT 100;
```

### Get Ledger History for Account

```sql
SELECT le.*, p.description
FROM ledger_entries le
JOIN payments p ON le.payment_id = p.id
WHERE le.account_id = $1
ORDER BY le.created_at DESC
LIMIT 100;
```

### Get Unpublished Outbox Events

```sql
SELECT *
FROM outbox
WHERE published_at IS NULL
ORDER BY created_at ASC
LIMIT 100;
```

### Clean Up Expired Idempotency Keys

```sql
DELETE FROM idempotency_keys
WHERE expires_at < NOW();
```
