from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.exceptions import OptimisticLockError
from payment_service.domain.models import AccountBalance


class BalanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: str) -> AccountBalance | None:
        result = await self._session.execute(
            text("""
                SELECT account_id, available_balance_cents, pending_balance_cents,
                       currency, version, updated_at
                FROM account_balances
                WHERE account_id = :account_id
            """),
            {"account_id": account_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return AccountBalance(
            account_id=row.account_id,
            available_balance_cents=row.available_balance_cents,
            pending_balance_cents=row.pending_balance_cents,
            currency=row.currency,
            version=row.version,
            updated_at=row.updated_at,
        )

    async def get_for_update(self, account_id: str) -> AccountBalance | None:
        result = await self._session.execute(
            text("""
                SELECT account_id, available_balance_cents, pending_balance_cents,
                       currency, version, updated_at
                FROM account_balances
                WHERE account_id = :account_id
                FOR UPDATE
            """),
            {"account_id": account_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return AccountBalance(
            account_id=row.account_id,
            available_balance_cents=row.available_balance_cents,
            pending_balance_cents=row.pending_balance_cents,
            currency=row.currency,
            version=row.version,
            updated_at=row.updated_at,
        )

    async def add(self, balance: AccountBalance) -> None:
        await self._session.execute(
            text("""
                INSERT INTO account_balances
                    (account_id, available_balance_cents, pending_balance_cents,
                     currency, version, updated_at)
                VALUES
                    (:account_id, :available_balance_cents, :pending_balance_cents,
                     :currency, :version, :updated_at)
            """),
            {
                "account_id": balance.account_id,
                "available_balance_cents": balance.available_balance_cents,
                "pending_balance_cents": balance.pending_balance_cents,
                "currency": balance.currency,
                "version": balance.version,
                "updated_at": balance.updated_at,
            },
        )

    async def update(
        self,
        account_id: str,
        new_available_balance: int,
        expected_version: int,
    ) -> None:
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                text("""
                    UPDATE account_balances
                    SET available_balance_cents = :new_balance,
                        version = version + 1,
                        updated_at = :updated_at
                    WHERE account_id = :account_id AND version = :expected_version
                """),
                {
                    "account_id": account_id,
                    "new_balance": new_available_balance,
                    "expected_version": expected_version,
                    "updated_at": datetime.now(UTC),
                },
            ),
        )
        if (result.rowcount or 0) == 0:
            raise OptimisticLockError("AccountBalance", account_id)
