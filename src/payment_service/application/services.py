from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from payment_service.application.unit_of_work import UnitOfWork
from payment_service.domain.models import (
    AccountBalance,
    EntryType,
    LedgerEntry,
    Money,
    Payment,
    PaymentStatus,
)


logger = structlog.get_logger()


@dataclass
class AuthorizePaymentCommand:
    idempotency_key: str
    payer_account_id: str
    payee_account_id: str
    amount_cents: int
    currency: str
    description: str | None = None


@dataclass
class AuthorizePaymentResult:
    payment_id: str
    status: PaymentStatus
    error_code: str | None = None
    error_message: str | None = None
    processed_at: datetime | None = None


class PaymentService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def authorize_payment(self, cmd: AuthorizePaymentCommand) -> AuthorizePaymentResult:
        log = logger.bind(
            idempotency_key=cmd.idempotency_key,
            payer=cmd.payer_account_id,
            payee=cmd.payee_account_id,
            amount_cents=cmd.amount_cents,
        )

        async with self.uow:
            existing = await self.uow.idempotency.get(cmd.idempotency_key)
            if existing and existing.status == "COMPLETED":
                log.info("idempotent_replay", payment_id=existing.payment_id)
                return AuthorizePaymentResult(
                    payment_id=existing.payment_id or "",
                    status=PaymentStatus.DUPLICATE,
                    processed_at=existing.created_at,
                )

            if not existing:
                await self.uow.idempotency.create(
                    key=cmd.idempotency_key,
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                )

            result = await self._validate_and_create_payment(cmd, log)
            if result.status == PaymentStatus.DECLINED:
                await self.uow.idempotency.mark_failed(cmd.idempotency_key)
                await self.uow.commit()
                return result

            payment = Payment.create(
                idempotency_key=cmd.idempotency_key,
                payer_id=cmd.payer_account_id,
                payee_id=cmd.payee_account_id,
                amount=Money(cmd.amount_cents, cmd.currency),
                description=cmd.description,
            )

            await self.uow.payments.add(payment)
            await self._execute_transfer(payment, log)

            await self.uow.outbox.add(
                aggregate_type="Payment",
                aggregate_id=payment.id,
                event_type="PaymentAuthorized",
                payload={
                    "payment_id": payment.id,
                    "payer_account_id": payment.payer_account_id,
                    "payee_account_id": payment.payee_account_id,
                    "amount_cents": payment.amount_cents,
                    "currency": payment.currency,
                },
            )

            await self.uow.idempotency.mark_completed(
                key=cmd.idempotency_key,
                payment_id=payment.id,
            )

            await self.uow.commit()

            log.info("payment_completed", step="4/4", payment_id=payment.id, status="AUTHORIZED")

            return AuthorizePaymentResult(
                payment_id=payment.id,
                status=PaymentStatus.AUTHORIZED,
                processed_at=payment.created_at,
            )

    async def _validate_and_create_payment(
        self, cmd: AuthorizePaymentCommand, log: structlog.stdlib.BoundLogger
    ) -> AuthorizePaymentResult:
        if cmd.amount_cents <= 0:
            return AuthorizePaymentResult(
                payment_id="",
                status=PaymentStatus.DECLINED,
                error_code="INVALID_AMOUNT",
                error_message="Amount must be positive",
                processed_at=datetime.now(UTC),
            )

        if cmd.payer_account_id == cmd.payee_account_id:
            return AuthorizePaymentResult(
                payment_id="",
                status=PaymentStatus.DECLINED,
                error_code="SAME_ACCOUNT",
                error_message="Cannot transfer to same account",
                processed_at=datetime.now(UTC),
            )

        payer = await self.uow.accounts.get(cmd.payer_account_id)
        if not payer:
            return AuthorizePaymentResult(
                payment_id="",
                status=PaymentStatus.DECLINED,
                error_code="ACCOUNT_NOT_FOUND",
                error_message=f"Payer account {cmd.payer_account_id} not found",
                processed_at=datetime.now(UTC),
            )

        payee = await self.uow.accounts.get(cmd.payee_account_id)
        if not payee:
            return AuthorizePaymentResult(
                payment_id="",
                status=PaymentStatus.DECLINED,
                error_code="ACCOUNT_NOT_FOUND",
                error_message=f"Payee account {cmd.payee_account_id} not found",
                processed_at=datetime.now(UTC),
            )

        payer_balance = await self.uow.balances.get(cmd.payer_account_id)
        if not payer_balance or payer_balance.available_balance_cents < cmd.amount_cents:
            log.info(
                "payment_declined",
                reason="INSUFFICIENT_FUNDS",
                available=payer_balance.available_balance_cents if payer_balance else 0,
                required=cmd.amount_cents,
            )
            return AuthorizePaymentResult(
                payment_id="",
                status=PaymentStatus.DECLINED,
                error_code="INSUFFICIENT_FUNDS",
                error_message="Insufficient funds",
                processed_at=datetime.now(UTC),
            )

        log.info(
            "payment_validated",
            step="1/4",
            payer=cmd.payer_account_id,
            payee=cmd.payee_account_id,
            amount=cmd.amount_cents,
        )

        return AuthorizePaymentResult(
            payment_id="",
            status=PaymentStatus.AUTHORIZED,
            processed_at=datetime.now(UTC),
        )

    async def _execute_transfer(self, payment: Payment, log: structlog.stdlib.BoundLogger) -> None:
        payer_balance = await self.uow.balances.get_for_update(payment.payer_account_id)
        payee_balance = await self.uow.balances.get_for_update(payment.payee_account_id)

        if payer_balance is None:
            raise ValueError(f"Payer balance not found: {payment.payer_account_id}")
        if payee_balance is None:
            raise ValueError(f"Payee balance not found: {payment.payee_account_id}")

        if payer_balance.available_balance_cents < payment.amount_cents:
            raise ValueError(
                f"Insufficient funds after lock: {payment.payer_account_id} "
                f"has {payer_balance.available_balance_cents}, needs {payment.amount_cents}"
            )

        new_payer_balance = payer_balance.available_balance_cents - payment.amount_cents
        new_payee_balance = payee_balance.available_balance_cents + payment.amount_cents

        log.info(
            "payment_transferring",
            step="2/4",
            payer_balance_before=payer_balance.available_balance_cents,
            payee_balance_before=payee_balance.available_balance_cents,
            amount=payment.amount_cents,
        )

        debit_entry = LedgerEntry.create(
            payment_id=payment.id,
            account_id=payment.payer_account_id,
            entry_type=EntryType.DEBIT,
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            balance_after_cents=new_payer_balance,
        )

        credit_entry = LedgerEntry.create(
            payment_id=payment.id,
            account_id=payment.payee_account_id,
            entry_type=EntryType.CREDIT,
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            balance_after_cents=new_payee_balance,
        )

        await self.uow.ledger.add(debit_entry)
        await self.uow.ledger.add(credit_entry)

        await self.uow.balances.update(
            payment.payer_account_id,
            new_payer_balance,
            payer_balance.version,
        )
        await self.uow.balances.update(
            payment.payee_account_id,
            new_payee_balance,
            payee_balance.version,
        )

        log.info(
            "payment_ledger_created",
            step="3/4",
            payer_balance_after=new_payer_balance,
            payee_balance_after=new_payee_balance,
        )

    async def get_payment(self, payment_id: str) -> Payment | None:
        payment = await self.uow.payments.get(payment_id)
        if payment:
            logger.info(
                "get_payment",
                payment_id=payment.id,
                status=payment.status.value,
                amount=payment.amount_cents,
            )
        return payment

    async def get_account_balance(self, account_id: str) -> AccountBalance | None:
        balance = await self.uow.balances.get(account_id)
        if balance:
            logger.info(
                "get_balance",
                account_id=account_id,
                available=balance.available_balance_cents,
            )
        return balance
