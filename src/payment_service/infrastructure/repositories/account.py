from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.models import Account


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: str) -> Account | None:
        result = await self._session.execute(
            text("""
                SELECT id, owner_id, currency, status, created_at, updated_at
                FROM accounts
                WHERE id = :id
            """),
            {"id": account_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return Account(
            id=row.id,
            owner_id=row.owner_id,
            currency=row.currency,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def add(self, account: Account) -> None:
        await self._session.execute(
            text("""
                INSERT INTO accounts (id, owner_id, currency, status, created_at, updated_at)
                VALUES (:id, :owner_id, :currency, :status, :created_at, :updated_at)
            """),
            {
                "id": account.id,
                "owner_id": account.owner_id,
                "currency": account.currency,
                "status": account.status,
                "created_at": account.created_at,
                "updated_at": account.updated_at,
            },
        )

    async def update_status(self, account_id: str, status: str) -> None:
        await self._session.execute(
            text("""
                UPDATE accounts
                SET status = :status, updated_at = :updated_at
                WHERE id = :id
            """),
            {
                "id": account_id,
                "status": status,
                "updated_at": datetime.now(UTC),
            },
        )
