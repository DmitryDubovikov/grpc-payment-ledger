from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.models import Payment, PaymentStatus


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payment_id: str) -> Payment | None:
        result = await self._session.execute(
            text("""
                SELECT id, idempotency_key, payer_account_id, payee_account_id,
                       amount_cents, currency, status, description,
                       error_code, error_message, created_at, updated_at
                FROM payments
                WHERE id = :id
            """),
            {"id": payment_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return Payment(
            id=row.id,
            idempotency_key=row.idempotency_key,
            payer_account_id=row.payer_account_id,
            payee_account_id=row.payee_account_id,
            amount_cents=row.amount_cents,
            currency=row.currency,
            status=PaymentStatus(row.status),
            description=row.description,
            error_code=row.error_code,
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        result = await self._session.execute(
            text("""
                SELECT id, idempotency_key, payer_account_id, payee_account_id,
                       amount_cents, currency, status, description,
                       error_code, error_message, created_at, updated_at
                FROM payments
                WHERE idempotency_key = :key
            """),
            {"key": key},
        )
        row = result.fetchone()
        if not row:
            return None
        return Payment(
            id=row.id,
            idempotency_key=row.idempotency_key,
            payer_account_id=row.payer_account_id,
            payee_account_id=row.payee_account_id,
            amount_cents=row.amount_cents,
            currency=row.currency,
            status=PaymentStatus(row.status),
            description=row.description,
            error_code=row.error_code,
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def add(self, payment: Payment) -> None:
        await self._session.execute(
            text("""
                INSERT INTO payments
                    (id, idempotency_key, payer_account_id, payee_account_id,
                     amount_cents, currency, status, description,
                     error_code, error_message, created_at, updated_at)
                VALUES
                    (:id, :idempotency_key, :payer_account_id, :payee_account_id,
                     :amount_cents, :currency, :status, :description,
                     :error_code, :error_message, :created_at, :updated_at)
            """),
            {
                "id": payment.id,
                "idempotency_key": payment.idempotency_key,
                "payer_account_id": payment.payer_account_id,
                "payee_account_id": payment.payee_account_id,
                "amount_cents": payment.amount_cents,
                "currency": payment.currency,
                "status": payment.status.value,
                "description": payment.description,
                "error_code": payment.error_code,
                "error_message": payment.error_message,
                "created_at": payment.created_at,
                "updated_at": payment.updated_at,
            },
        )

    async def update_status(
        self,
        payment_id: str,
        status: PaymentStatus,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        await self._session.execute(
            text("""
                UPDATE payments
                SET status = :status,
                    error_code = :error_code,
                    error_message = :error_message,
                    updated_at = :updated_at
                WHERE id = :id
            """),
            {
                "id": payment_id,
                "status": status.value,
                "error_code": error_code,
                "error_message": error_message,
                "updated_at": datetime.now(UTC),
            },
        )
