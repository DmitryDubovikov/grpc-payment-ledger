-- Initialize test data for manual testing
-- Run with: make init-test-data

-- Create payer account with $1000
INSERT INTO accounts (id, owner_id, currency, status, created_at, updated_at)
VALUES ('acc-payer-001', 'owner-001', 'USD', 'ACTIVE', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO account_balances (account_id, available_balance_cents, pending_balance_cents, currency, version, updated_at)
VALUES ('acc-payer-001', 100000, 0, 'USD', 1, NOW())
ON CONFLICT (account_id) DO UPDATE SET
    available_balance_cents = 100000,
    pending_balance_cents = 0,
    version = 1,
    updated_at = NOW();

-- Create payee account with $500
INSERT INTO accounts (id, owner_id, currency, status, created_at, updated_at)
VALUES ('acc-payee-002', 'owner-002', 'USD', 'ACTIVE', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO account_balances (account_id, available_balance_cents, pending_balance_cents, currency, version, updated_at)
VALUES ('acc-payee-002', 50000, 0, 'USD', 1, NOW())
ON CONFLICT (account_id) DO UPDATE SET
    available_balance_cents = 50000,
    pending_balance_cents = 0,
    version = 1,
    updated_at = NOW();

-- Verify
SELECT 'Accounts:' as info;
SELECT id, owner_id, currency, status FROM accounts;

SELECT 'Balances:' as info;
SELECT account_id, available_balance_cents, pending_balance_cents, currency FROM account_balances;
