from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.models import IdempotencyRecord


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> IdempotencyRecord | None:
        result = await self._session.execute(
            text("""
                SELECT key, payment_id, response_data, status, created_at, expires_at
                FROM idempotency_keys
                WHERE key = :key AND expires_at > :now
            """),
            {"key": key, "now": datetime.now(UTC)},
        )
        row = result.fetchone()
        if not row:
            return None
        return IdempotencyRecord(
            key=row.key,
            payment_id=row.payment_id,
            response_data=row.response_data,
            status=row.status,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )

    async def create(self, key: str, expires_at: datetime) -> None:
        await self._session.execute(
            text("""
                INSERT INTO idempotency_keys (key, status, created_at, expires_at)
                VALUES (:key, 'PENDING', :created_at, :expires_at)
                ON CONFLICT (key) DO NOTHING
            """),
            {
                "key": key,
                "created_at": datetime.now(UTC),
                "expires_at": expires_at,
            },
        )

    async def mark_completed(
        self,
        key: str,
        payment_id: str,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        await self._session.execute(
            text("""
                UPDATE idempotency_keys
                SET status = 'COMPLETED',
                    payment_id = :payment_id,
                    response_data = :response_data
                WHERE key = :key
            """),
            {
                "key": key,
                "payment_id": payment_id,
                "response_data": response_data,
            },
        )

    async def mark_failed(self, key: str) -> None:
        await self._session.execute(
            text("""
                UPDATE idempotency_keys
                SET status = 'FAILED'
                WHERE key = :key
            """),
            {"key": key},
        )

    async def delete_expired(self) -> int:
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                text("""
                    DELETE FROM idempotency_keys
                    WHERE expires_at < :now
                """),
                {"now": datetime.now(UTC)},
            ),
        )
        return result.rowcount or 0
