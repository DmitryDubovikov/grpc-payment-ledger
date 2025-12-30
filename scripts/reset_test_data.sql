-- Reset all test data for clean manual testing
-- Run with: make reset-test-data

-- Clear all transactional data (order matters due to FK constraints)
TRUNCATE TABLE ledger_entries CASCADE;
TRUNCATE TABLE outbox CASCADE;
TRUNCATE TABLE idempotency_keys CASCADE;
TRUNCATE TABLE payments CASCADE;
TRUNCATE TABLE account_balances CASCADE;
TRUNCATE TABLE accounts CASCADE;

-- Re-create test accounts

-- Payer account with $1000
INSERT INTO accounts (id, owner_id, currency, status, created_at, updated_at)
VALUES ('acc-payer-001', 'owner-001', 'USD', 'ACTIVE', NOW(), NOW());

INSERT INTO account_balances (account_id, available_balance_cents, pending_balance_cents, currency, version, updated_at)
VALUES ('acc-payer-001', 100000, 0, 'USD', 1, NOW());

-- Payee account with $500
INSERT INTO accounts (id, owner_id, currency, status, created_at, updated_at)
VALUES ('acc-payee-002', 'owner-002', 'USD', 'ACTIVE', NOW(), NOW());

INSERT INTO account_balances (account_id, available_balance_cents, pending_balance_cents, currency, version, updated_at)
VALUES ('acc-payee-002', 50000, 0, 'USD', 1, NOW());

-- Verify
SELECT 'Test data reset complete' as status;
SELECT 'Accounts:' as info;
SELECT id, owner_id, currency, status FROM accounts;
SELECT 'Balances:' as info;
SELECT account_id, available_balance_cents, pending_balance_cents, currency FROM account_balances;
