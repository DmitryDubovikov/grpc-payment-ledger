from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.models import EntryType, LedgerEntry


class LedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: LedgerEntry) -> None:
        await self._session.execute(
            text("""
                INSERT INTO ledger_entries
                    (id, payment_id, account_id, entry_type, amount_cents,
                     currency, balance_after_cents, created_at)
                VALUES
                    (:id, :payment_id, :account_id, :entry_type, :amount_cents,
                     :currency, :balance_after_cents, :created_at)
            """),
            {
                "id": entry.id,
                "payment_id": entry.payment_id,
                "account_id": entry.account_id,
                "entry_type": entry.entry_type.value,
                "amount_cents": entry.amount_cents,
                "currency": entry.currency,
                "balance_after_cents": entry.balance_after_cents,
                "created_at": entry.created_at,
            },
        )

    async def get_by_payment_id(self, payment_id: str) -> list[LedgerEntry]:
        result = await self._session.execute(
            text("""
                SELECT id, payment_id, account_id, entry_type, amount_cents,
                       currency, balance_after_cents, created_at
                FROM ledger_entries
                WHERE payment_id = :payment_id
                ORDER BY created_at
            """),
            {"payment_id": payment_id},
        )
        rows = result.fetchall()
        return [
            LedgerEntry(
                id=row.id,
                payment_id=row.payment_id,
                account_id=row.account_id,
                entry_type=EntryType(row.entry_type),
                amount_cents=row.amount_cents,
                currency=row.currency,
                balance_after_cents=row.balance_after_cents,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def get_by_account_id(self, account_id: str, limit: int = 100) -> list[LedgerEntry]:
        result = await self._session.execute(
            text("""
                SELECT id, payment_id, account_id, entry_type, amount_cents,
                       currency, balance_after_cents, created_at
                FROM ledger_entries
                WHERE account_id = :account_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"account_id": account_id, "limit": limit},
        )
        rows = result.fetchall()
        return [
            LedgerEntry(
                id=row.id,
                payment_id=row.payment_id,
                account_id=row.account_id,
                entry_type=EntryType(row.entry_type),
                amount_cents=row.amount_cents,
                currency=row.currency,
                balance_after_cents=row.balance_after_cents,
                created_at=row.created_at,
            )
            for row in rows
        ]
