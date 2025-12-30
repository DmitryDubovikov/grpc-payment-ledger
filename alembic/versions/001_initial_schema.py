"""Initial schema: accounts, payments, ledger, idempotency, outbox

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_accounts_owner_id", "accounts", ["owner_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("payer_account_id", sa.String(26), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("payee_account_id", sa.String(26), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"], unique=True)
    op.create_index("ix_payments_payer_account_id", "payments", ["payer_account_id"])
    op.create_index("ix_payments_payee_account_id", "payments", ["payee_account_id"])
    op.create_index("ix_payments_created_at", "payments", ["created_at"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("payment_id", sa.String(26), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("account_id", sa.String(26), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("entry_type", sa.String(10), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("balance_after_cents", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ledger_entries_payment_id", "ledger_entries", ["payment_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])
    op.create_index("ix_ledger_entries_created_at", "ledger_entries", ["created_at"])

    op.create_table(
        "account_balances",
        sa.Column("account_id", sa.String(26), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("available_balance_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("pending_balance_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("version", sa.BigInteger, nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("payment_id", sa.String(26), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("response_data", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])

    op.create_table(
        "outbox",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(26), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index("ix_outbox_aggregate", "outbox", ["aggregate_type", "aggregate_id"])


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("idempotency_keys")
    op.drop_table("account_balances")
    op.drop_table("ledger_entries")
    op.drop_table("payments")
    op.drop_table("accounts")
