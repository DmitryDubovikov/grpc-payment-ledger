import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        event = OutboxEvent.create(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
        await self._session.execute(
            text("""
                INSERT INTO outbox
                    (id, aggregate_type, aggregate_id, event_type, payload,
                     created_at, retry_count)
                VALUES
                    (:id, :aggregate_type, :aggregate_id, :event_type, :payload,
                     :created_at, :retry_count)
            """),
            {
                "id": event.id,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "event_type": event.event_type,
                "payload": json.dumps(event.payload),
                "created_at": event.created_at,
                "retry_count": event.retry_count,
            },
        )
        return event

    async def get_unpublished(self, limit: int = 100) -> list[OutboxEvent]:
        result = await self._session.execute(
            text("""
                SELECT id, aggregate_type, aggregate_id, event_type, payload,
                       created_at, published_at, retry_count
                FROM outbox
                WHERE published_at IS NULL
                ORDER BY created_at
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            """),
            {"limit": limit},
        )
        rows = result.fetchall()
        return [
            OutboxEvent(
                id=row.id,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                event_type=row.event_type,
                payload=row.payload,
                created_at=row.created_at,
                published_at=row.published_at,
                retry_count=row.retry_count,
            )
            for row in rows
        ]

    async def mark_published(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        await self._session.execute(
            text("""
                UPDATE outbox
                SET published_at = NOW()
                WHERE id = ANY(:ids)
            """),
            {"ids": event_ids},
        )

    async def increment_retry_count(self, event_id: str) -> None:
        await self._session.execute(
            text("""
                UPDATE outbox
                SET retry_count = retry_count + 1
                WHERE id = :id
            """),
            {"id": event_id},
        )
