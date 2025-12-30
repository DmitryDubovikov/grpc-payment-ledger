from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ulid import ULID


class PaymentStatus(Enum):
    AUTHORIZED = "AUTHORIZED"
    DECLINED = "DECLINED"
    DUPLICATE = "DUPLICATE"


class EntryType(Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


@dataclass(frozen=True)
class Money:
    amount_cents: int
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount_cents < 0:
            raise ValueError("Amount cannot be negative")
        if len(self.currency) != 3:
            raise ValueError("Currency must be ISO 4217 code (3 characters)")


@dataclass
class Account:
    id: str
    owner_id: str
    currency: str = "USD"
    status: str = "ACTIVE"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AccountBalance:
    account_id: str
    available_balance_cents: int
    pending_balance_cents: int
    currency: str
    version: int = 1
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Payment:
    id: str
    idempotency_key: str
    payer_account_id: str
    payee_account_id: str
    amount_cents: int
    currency: str
    status: PaymentStatus
    description: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        idempotency_key: str,
        payer_id: str,
        payee_id: str,
        amount: Money,
        description: str | None = None,
    ) -> "Payment":
        return cls(
            id=str(ULID()),
            idempotency_key=idempotency_key,
            payer_account_id=payer_id,
            payee_account_id=payee_id,
            amount_cents=amount.amount_cents,
            currency=amount.currency,
            status=PaymentStatus.AUTHORIZED,
            description=description,
        )


@dataclass
class LedgerEntry:
    id: str
    payment_id: str
    account_id: str
    entry_type: EntryType
    amount_cents: int
    currency: str
    balance_after_cents: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        payment_id: str,
        account_id: str,
        entry_type: EntryType,
        amount_cents: int,
        currency: str,
        balance_after_cents: int,
    ) -> "LedgerEntry":
        return cls(
            id=str(ULID()),
            payment_id=payment_id,
            account_id=account_id,
            entry_type=entry_type,
            amount_cents=amount_cents,
            currency=currency,
            balance_after_cents=balance_after_cents,
        )


@dataclass
class IdempotencyRecord:
    key: str
    status: str
    payment_id: str | None = None
    response_data: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


@dataclass
class OutboxEvent:
    id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None
    retry_count: int = 0

    @classmethod
    def create(
        cls,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> "OutboxEvent":
        return cls(
            id=str(ULID()),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
