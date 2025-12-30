"""Unit tests for domain models and exceptions."""

from datetime import UTC, datetime

import pytest

from payment_service.domain.exceptions import (
    AccountNotFoundError,
    CurrencyMismatchError,
    DomainError,
    InsufficientFundsError,
    InvalidAmountError,
    OptimisticLockError,
    SameAccountError,
)
from payment_service.domain.models import (
    Account,
    AccountBalance,
    EntryType,
    IdempotencyRecord,
    LedgerEntry,
    Money,
    OutboxEvent,
    Payment,
    PaymentStatus,
)


class TestMoney:
    """Tests for Money value object."""

    def test_money_creation_success(self) -> None:
        """Valid Money object can be created."""
        money = Money(amount_cents=1000, currency="USD")
        assert money.amount_cents == 1000
        assert money.currency == "USD"

    def test_money_with_zero_amount(self) -> None:
        """Money with zero amount is valid."""
        money = Money(amount_cents=0, currency="USD")
        assert money.amount_cents == 0
        assert money.currency == "USD"

    def test_money_cannot_be_negative(self) -> None:
        """Money amount cannot be negative."""
        with pytest.raises(ValueError, match="cannot be negative"):
            Money(amount_cents=-100, currency="USD")

    def test_money_requires_3_char_currency(self) -> None:
        """Money requires ISO 4217 currency code (3 characters)."""
        with pytest.raises(ValueError, match="ISO 4217"):
            Money(amount_cents=100, currency="INVALID")

    def test_money_rejects_short_currency(self) -> None:
        """Money rejects currency codes shorter than 3 characters."""
        with pytest.raises(ValueError, match="ISO 4217"):
            Money(amount_cents=100, currency="US")

    def test_money_rejects_empty_currency(self) -> None:
        """Money rejects empty currency code."""
        with pytest.raises(ValueError, match="ISO 4217"):
            Money(amount_cents=100, currency="")

    def test_money_is_immutable(self) -> None:
        """Money is a frozen dataclass (immutable)."""
        money = Money(amount_cents=1000, currency="USD")
        with pytest.raises(AttributeError):
            money.amount_cents = 2000  # type: ignore[misc]

    def test_money_equality(self) -> None:
        """Two Money objects with same values are equal."""
        money1 = Money(amount_cents=1000, currency="USD")
        money2 = Money(amount_cents=1000, currency="USD")
        assert money1 == money2

    def test_money_inequality_different_amount(self) -> None:
        """Money objects with different amounts are not equal."""
        money1 = Money(amount_cents=1000, currency="USD")
        money2 = Money(amount_cents=2000, currency="USD")
        assert money1 != money2

    def test_money_inequality_different_currency(self) -> None:
        """Money objects with different currencies are not equal."""
        money1 = Money(amount_cents=1000, currency="USD")
        money2 = Money(amount_cents=1000, currency="EUR")
        assert money1 != money2

    def test_money_various_currencies(self) -> None:
        """Money accepts various valid currency codes."""
        currencies = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"]
        for currency in currencies:
            money = Money(amount_cents=100, currency=currency)
            assert money.currency == currency

    def test_money_default_currency(self) -> None:
        """Money defaults to USD currency."""
        money = Money(amount_cents=100)
        assert money.currency == "USD"


class TestPaymentStatus:
    """Tests for PaymentStatus enum."""

    def test_payment_status_values(self) -> None:
        """PaymentStatus has expected values."""
        assert PaymentStatus.AUTHORIZED.value == "AUTHORIZED"
        assert PaymentStatus.DECLINED.value == "DECLINED"
        assert PaymentStatus.DUPLICATE.value == "DUPLICATE"

    def test_payment_status_from_string(self) -> None:
        """PaymentStatus can be created from string."""
        assert PaymentStatus("AUTHORIZED") == PaymentStatus.AUTHORIZED
        assert PaymentStatus("DECLINED") == PaymentStatus.DECLINED
        assert PaymentStatus("DUPLICATE") == PaymentStatus.DUPLICATE


class TestEntryType:
    """Tests for EntryType enum."""

    def test_entry_type_values(self) -> None:
        """EntryType has expected values."""
        assert EntryType.DEBIT.value == "DEBIT"
        assert EntryType.CREDIT.value == "CREDIT"


class TestAccount:
    """Tests for Account entity."""

    def test_account_creation(self) -> None:
        """Account can be created with required fields."""
        account = Account(
            id="acc-001",
            owner_id="owner-001",
            currency="USD",
            status="ACTIVE",
        )
        assert account.id == "acc-001"
        assert account.owner_id == "owner-001"
        assert account.currency == "USD"
        assert account.status == "ACTIVE"
        assert account.created_at is not None
        assert account.updated_at is not None

    def test_account_default_values(self) -> None:
        """Account has correct default values."""
        account = Account(id="acc-001", owner_id="owner-001")
        assert account.currency == "USD"
        assert account.status == "ACTIVE"

    def test_account_timestamps_are_utc(self) -> None:
        """Account timestamps are in UTC."""
        account = Account(id="acc-001", owner_id="owner-001")
        assert account.created_at.tzinfo == UTC
        assert account.updated_at.tzinfo == UTC


class TestAccountBalance:
    """Tests for AccountBalance entity."""

    def test_account_balance_creation(self) -> None:
        """AccountBalance can be created with all fields."""
        balance = AccountBalance(
            account_id="acc-001",
            available_balance_cents=10000,
            pending_balance_cents=500,
            currency="USD",
            version=1,
        )
        assert balance.account_id == "acc-001"
        assert balance.available_balance_cents == 10000
        assert balance.pending_balance_cents == 500
        assert balance.currency == "USD"
        assert balance.version == 1

    def test_account_balance_default_version(self) -> None:
        """AccountBalance defaults to version 1."""
        balance = AccountBalance(
            account_id="acc-001",
            available_balance_cents=10000,
            pending_balance_cents=0,
            currency="USD",
        )
        assert balance.version == 1

    def test_account_balance_negative_available(self) -> None:
        """AccountBalance allows negative available balance (for testing edge cases)."""
        # Note: Business logic should prevent this, but the model allows it
        balance = AccountBalance(
            account_id="acc-001",
            available_balance_cents=-100,
            pending_balance_cents=0,
            currency="USD",
        )
        assert balance.available_balance_cents == -100


class TestPayment:
    """Tests for Payment entity."""

    def test_payment_create_success(self) -> None:
        """Payment.create generates valid payment."""
        payment = Payment.create(
            idempotency_key="test-key-123",
            payer_id="payer-001",
            payee_id="payee-001",
            amount=Money(1000, "USD"),
            description="Test payment",
        )

        assert payment.status == PaymentStatus.AUTHORIZED
        assert payment.amount_cents == 1000
        assert payment.currency == "USD"
        assert payment.description == "Test payment"
        assert payment.idempotency_key == "test-key-123"
        assert payment.payer_account_id == "payer-001"
        assert payment.payee_account_id == "payee-001"
        assert len(payment.id) == 26  # ULID length

    def test_payment_create_without_description(self) -> None:
        """Payment can be created without description."""
        payment = Payment.create(
            idempotency_key="test-key-456",
            payer_id="payer-001",
            payee_id="payee-001",
            amount=Money(5000, "EUR"),
        )

        assert payment.description is None
        assert payment.currency == "EUR"
        assert payment.amount_cents == 5000

    def test_payment_create_generates_unique_ids(self) -> None:
        """Payment.create generates unique IDs for each payment."""
        payment1 = Payment.create(
            idempotency_key="key-1",
            payer_id="payer",
            payee_id="payee",
            amount=Money(100, "USD"),
        )
        payment2 = Payment.create(
            idempotency_key="key-2",
            payer_id="payer",
            payee_id="payee",
            amount=Money(100, "USD"),
        )

        assert payment1.id != payment2.id

    def test_payment_initial_state(self) -> None:
        """Payment is created in AUTHORIZED state with no errors."""
        payment = Payment.create(
            idempotency_key="test-key",
            payer_id="payer",
            payee_id="payee",
            amount=Money(100, "USD"),
        )

        assert payment.status == PaymentStatus.AUTHORIZED
        assert payment.error_code is None
        assert payment.error_message is None

    def test_payment_direct_creation(self) -> None:
        """Payment can be created directly with all fields."""
        payment = Payment(
            id="pay-001",
            idempotency_key="key-001",
            payer_account_id="payer-001",
            payee_account_id="payee-001",
            amount_cents=1000,
            currency="USD",
            status=PaymentStatus.DECLINED,
            error_code="INSUFFICIENT_FUNDS",
            error_message="Not enough balance",
        )

        assert payment.status == PaymentStatus.DECLINED
        assert payment.error_code == "INSUFFICIENT_FUNDS"


class TestLedgerEntry:
    """Tests for LedgerEntry entity."""

    def test_ledger_entry_create_debit(self) -> None:
        """LedgerEntry.create generates valid debit entry."""
        entry = LedgerEntry.create(
            payment_id="pay-001",
            account_id="acc-001",
            entry_type=EntryType.DEBIT,
            amount_cents=1000,
            currency="USD",
            balance_after_cents=9000,
        )

        assert entry.payment_id == "pay-001"
        assert entry.account_id == "acc-001"
        assert entry.entry_type == EntryType.DEBIT
        assert entry.amount_cents == 1000
        assert entry.balance_after_cents == 9000
        assert len(entry.id) == 26  # ULID length

    def test_ledger_entry_create_credit(self) -> None:
        """LedgerEntry.create generates valid credit entry."""
        entry = LedgerEntry.create(
            payment_id="pay-001",
            account_id="acc-002",
            entry_type=EntryType.CREDIT,
            amount_cents=1000,
            currency="USD",
            balance_after_cents=11000,
        )

        assert entry.entry_type == EntryType.CREDIT
        assert entry.balance_after_cents == 11000

    def test_ledger_entry_generates_unique_ids(self) -> None:
        """LedgerEntry.create generates unique IDs."""
        entry1 = LedgerEntry.create(
            payment_id="pay-001",
            account_id="acc-001",
            entry_type=EntryType.DEBIT,
            amount_cents=100,
            currency="USD",
            balance_after_cents=900,
        )
        entry2 = LedgerEntry.create(
            payment_id="pay-001",
            account_id="acc-002",
            entry_type=EntryType.CREDIT,
            amount_cents=100,
            currency="USD",
            balance_after_cents=1100,
        )

        assert entry1.id != entry2.id

    def test_ledger_entry_timestamp(self) -> None:
        """LedgerEntry has UTC timestamp."""
        entry = LedgerEntry.create(
            payment_id="pay-001",
            account_id="acc-001",
            entry_type=EntryType.DEBIT,
            amount_cents=100,
            currency="USD",
            balance_after_cents=900,
        )

        assert entry.created_at.tzinfo == UTC


class TestIdempotencyRecord:
    """Tests for IdempotencyRecord entity."""

    def test_idempotency_record_creation(self) -> None:
        """IdempotencyRecord can be created with required fields."""
        record = IdempotencyRecord(
            key="idem-key-001",
            status="PENDING",
        )

        assert record.key == "idem-key-001"
        assert record.status == "PENDING"
        assert record.payment_id is None
        assert record.response_data is None

    def test_idempotency_record_completed(self) -> None:
        """IdempotencyRecord can be created with completed status."""
        record = IdempotencyRecord(
            key="idem-key-002",
            status="COMPLETED",
            payment_id="pay-001",
            response_data={"status": "AUTHORIZED"},
        )

        assert record.status == "COMPLETED"
        assert record.payment_id == "pay-001"
        assert record.response_data == {"status": "AUTHORIZED"}

    def test_idempotency_record_with_expiry(self) -> None:
        """IdempotencyRecord can have expiry time."""
        expires_at = datetime.now(UTC)
        record = IdempotencyRecord(
            key="idem-key-003",
            status="PENDING",
            expires_at=expires_at,
        )

        assert record.expires_at == expires_at


class TestOutboxEvent:
    """Tests for OutboxEvent entity."""

    def test_outbox_event_create(self) -> None:
        """OutboxEvent.create generates valid event."""
        event = OutboxEvent.create(
            aggregate_type="Payment",
            aggregate_id="pay-001",
            event_type="PaymentAuthorized",
            payload={
                "payment_id": "pay-001",
                "amount_cents": 1000,
                "currency": "USD",
            },
        )

        assert event.aggregate_type == "Payment"
        assert event.aggregate_id == "pay-001"
        assert event.event_type == "PaymentAuthorized"
        assert event.payload["payment_id"] == "pay-001"
        assert len(event.id) == 26  # ULID length
        assert event.published_at is None
        assert event.retry_count == 0

    def test_outbox_event_generates_unique_ids(self) -> None:
        """OutboxEvent.create generates unique IDs."""
        event1 = OutboxEvent.create(
            aggregate_type="Payment",
            aggregate_id="pay-001",
            event_type="PaymentAuthorized",
            payload={},
        )
        event2 = OutboxEvent.create(
            aggregate_type="Payment",
            aggregate_id="pay-002",
            event_type="PaymentAuthorized",
            payload={},
        )

        assert event1.id != event2.id

    def test_outbox_event_direct_creation(self) -> None:
        """OutboxEvent can be created directly with all fields."""
        published_at = datetime.now(UTC)
        event = OutboxEvent(
            id="evt-001",
            aggregate_type="Payment",
            aggregate_id="pay-001",
            event_type="PaymentAuthorized",
            payload={"test": "data"},
            published_at=published_at,
            retry_count=3,
        )

        assert event.id == "evt-001"
        assert event.published_at == published_at
        assert event.retry_count == 3


class TestDomainExceptions:
    """Tests for domain exceptions."""

    def test_domain_error_is_base_exception(self) -> None:
        """DomainError is the base for all domain exceptions."""
        error = DomainError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_insufficient_funds_error(self) -> None:
        """InsufficientFundsError contains account and amount details."""
        error = InsufficientFundsError(
            account_id="acc-001",
            required=1000,
            available=500,
        )

        assert isinstance(error, DomainError)
        assert error.account_id == "acc-001"
        assert error.required == 1000
        assert error.available == 500
        assert "acc-001" in str(error)
        assert "1000" in str(error)
        assert "500" in str(error)

    def test_account_not_found_error(self) -> None:
        """AccountNotFoundError contains account ID."""
        error = AccountNotFoundError(account_id="acc-001")

        assert isinstance(error, DomainError)
        assert error.account_id == "acc-001"
        assert "acc-001" in str(error)

    def test_invalid_amount_error(self) -> None:
        """InvalidAmountError contains amount and reason."""
        error = InvalidAmountError(
            amount=-100,
            reason="Amount must be positive",
        )

        assert isinstance(error, DomainError)
        assert error.amount == -100
        assert error.reason == "Amount must be positive"
        assert "-100" in str(error)

    def test_same_account_error(self) -> None:
        """SameAccountError contains account ID."""
        error = SameAccountError(account_id="acc-001")

        assert isinstance(error, DomainError)
        assert error.account_id == "acc-001"
        assert "acc-001" in str(error)

    def test_optimistic_lock_error(self) -> None:
        """OptimisticLockError contains entity info."""
        error = OptimisticLockError(
            entity="AccountBalance",
            entity_id="acc-001",
        )

        assert isinstance(error, DomainError)
        assert error.entity == "AccountBalance"
        assert error.entity_id == "acc-001"
        assert "AccountBalance" in str(error)
        assert "acc-001" in str(error)

    def test_currency_mismatch_error(self) -> None:
        """CurrencyMismatchError contains expected and actual currencies."""
        error = CurrencyMismatchError(
            expected="USD",
            actual="EUR",
        )

        assert isinstance(error, DomainError)
        assert error.expected == "USD"
        assert error.actual == "EUR"
        assert "USD" in str(error)
        assert "EUR" in str(error)


class TestULIDGeneration:
    """Tests for ULID generation in models."""

    def test_payment_ulid_is_lexicographically_sortable(self) -> None:
        """Payment IDs are lexicographically sortable by creation time."""
        payment1 = Payment.create(
            idempotency_key="key-1",
            payer_id="payer",
            payee_id="payee",
            amount=Money(100, "USD"),
        )
        payment2 = Payment.create(
            idempotency_key="key-2",
            payer_id="payer",
            payee_id="payee",
            amount=Money(100, "USD"),
        )

        # Later created payment should have lexicographically larger ID
        assert payment1.id <= payment2.id

    def test_ulid_format(self) -> None:
        """ULID follows correct format (26 characters, Crockford Base32)."""
        payment = Payment.create(
            idempotency_key="key-1",
            payer_id="payer",
            payee_id="payee",
            amount=Money(100, "USD"),
        )

        # ULID is 26 characters
        assert len(payment.id) == 26

        # ULID uses Crockford Base32 alphabet (no I, L, O, U)
        valid_chars = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        assert all(c in valid_chars for c in payment.id.upper())
