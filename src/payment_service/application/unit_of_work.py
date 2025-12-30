from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.infrastructure.repositories import (
    AccountRepository,
    BalanceRepository,
    IdempotencyRepository,
    LedgerRepository,
    OutboxRepository,
    PaymentRepository,
)


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.accounts = AccountRepository(session)
        self.payments = PaymentRepository(session)
        self.ledger = LedgerRepository(session)
        self.idempotency = IdempotencyRepository(session)
        self.outbox = OutboxRepository(session)
        self.balances = BalanceRepository(session)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
