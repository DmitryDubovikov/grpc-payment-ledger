"""Unit tests for PaymentService with mocked dependencies."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from payment_service.application.services import (
    AuthorizePaymentCommand,
    PaymentService,
)
from payment_service.domain.models import (
    Account,
    AccountBalance,
    IdempotencyRecord,
    Payment,
    PaymentStatus,
)
from tests.conftest import create_account_balance


class TestPaymentServiceAuthorization:
    """Tests for PaymentService.authorize_payment."""

    @pytest.fixture
    def service(self, mock_uow: AsyncMock) -> PaymentService:
        """Create PaymentService with mocked UoW."""
        return PaymentService(mock_uow)

    @pytest.fixture
    def valid_command(self) -> AuthorizePaymentCommand:
        """Create valid authorization command."""
        return AuthorizePaymentCommand(
            idempotency_key="test-key-001",
            payer_account_id="payer-account-001",
            payee_account_id="payee-account-002",
            amount_cents=1000,
            currency="USD",
            description="Test payment",
        )

    @pytest.mark.asyncio
    async def test_authorize_payment_success(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Successful payment authorization."""
        # Setup mocks
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [
            sample_payer_account,
            sample_payee_account,
        ]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        result = await service.authorize_payment(valid_command)

        assert result.status == PaymentStatus.AUTHORIZED
        assert result.payment_id is not None
        assert len(result.payment_id) == 26  # ULID length
        assert result.error_code is None
        assert result.error_message is None
        mock_uow.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_authorize_payment_creates_idempotency_record(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Authorization creates idempotency record."""
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [
            sample_payer_account,
            sample_payee_account,
        ]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        await service.authorize_payment(valid_command)

        mock_uow.idempotency.create.assert_called_once()
        call_args = mock_uow.idempotency.create.call_args
        assert call_args.kwargs["key"] == valid_command.idempotency_key

    @pytest.mark.asyncio
    async def test_authorize_payment_saves_payment(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Authorization saves payment to repository."""
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [
            sample_payer_account,
            sample_payee_account,
        ]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        await service.authorize_payment(valid_command)

        mock_uow.payments.add.assert_called_once()
        saved_payment = mock_uow.payments.add.call_args[0][0]
        assert isinstance(saved_payment, Payment)
        assert saved_payment.amount_cents == valid_command.amount_cents
        assert saved_payment.currency == valid_command.currency
        assert saved_payment.payer_account_id == valid_command.payer_account_id
        assert saved_payment.payee_account_id == valid_command.payee_account_id

    @pytest.mark.asyncio
    async def test_authorize_payment_creates_ledger_entries(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Authorization creates debit and credit ledger entries."""
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [
            sample_payer_account,
            sample_payee_account,
        ]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        await service.authorize_payment(valid_command)

        # Should create exactly 2 ledger entries (debit + credit)
        assert mock_uow.ledger.add.call_count == 2

    @pytest.mark.asyncio
    async def test_authorize_payment_updates_balances(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Authorization updates payer and payee balances."""
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [
            sample_payer_account,
            sample_payee_account,
        ]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        await service.authorize_payment(valid_command)

        # Should update exactly 2 balances
        assert mock_uow.balances.update.call_count == 2

        # Check payer balance update (debit)
        payer_update = mock_uow.balances.update.call_args_list[0]
        assert payer_update[0][0] == valid_command.payer_account_id
        expected_payer_balance = sample_payer_balance.available_balance_cents - valid_command.amount_cents
        assert payer_update[0][1] == expected_payer_balance

        # Check payee balance update (credit)
        payee_update = mock_uow.balances.update.call_args_list[1]
        assert payee_update[0][0] == valid_command.payee_account_id
        expected_payee_balance = sample_payee_balance.available_balance_cents + valid_command.amount_cents
        assert payee_update[0][1] == expected_payee_balance

    @pytest.mark.asyncio
    async def test_authorize_payment_creates_outbox_event(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Authorization creates outbox event for publishing."""
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [
            sample_payer_account,
            sample_payee_account,
        ]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        await service.authorize_payment(valid_command)

        mock_uow.outbox.add.assert_called_once()
        call_kwargs = mock_uow.outbox.add.call_args.kwargs
        assert call_kwargs["aggregate_type"] == "Payment"
        assert call_kwargs["event_type"] == "PaymentAuthorized"
        assert call_kwargs["payload"]["amount_cents"] == valid_command.amount_cents

    @pytest.mark.asyncio
    async def test_authorize_payment_marks_idempotency_completed(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Authorization marks idempotency record as completed."""
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [
            sample_payer_account,
            sample_payee_account,
        ]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        result = await service.authorize_payment(valid_command)

        mock_uow.idempotency.mark_completed.assert_called_once()
        call_kwargs = mock_uow.idempotency.mark_completed.call_args.kwargs
        assert call_kwargs["key"] == valid_command.idempotency_key
        assert call_kwargs["payment_id"] == result.payment_id


class TestPaymentServiceIdempotency:
    """Tests for idempotency handling."""

    @pytest.fixture
    def service(self, mock_uow: AsyncMock) -> PaymentService:
        """Create PaymentService with mocked UoW."""
        return PaymentService(mock_uow)

    @pytest.fixture
    def valid_command(self) -> AuthorizePaymentCommand:
        """Create valid authorization command."""
        return AuthorizePaymentCommand(
            idempotency_key="existing-idempotency-key",
            payer_account_id="payer-account-001",
            payee_account_id="payee-account-002",
            amount_cents=1000,
            currency="USD",
        )

    @pytest.mark.asyncio
    async def test_idempotent_replay_returns_duplicate(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_idempotency_record: IdempotencyRecord,
    ) -> None:
        """Duplicate request returns cached result with DUPLICATE status."""
        mock_uow.idempotency.get.return_value = sample_idempotency_record

        result = await service.authorize_payment(valid_command)

        assert result.status == PaymentStatus.DUPLICATE
        assert result.payment_id == sample_idempotency_record.payment_id

    @pytest.mark.asyncio
    async def test_idempotent_replay_does_not_process_payment(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_idempotency_record: IdempotencyRecord,
    ) -> None:
        """Duplicate request does not reprocess payment."""
        mock_uow.idempotency.get.return_value = sample_idempotency_record

        await service.authorize_payment(valid_command)

        # Should not call any payment processing methods
        mock_uow.accounts.get.assert_not_called()
        mock_uow.balances.get.assert_not_called()
        mock_uow.payments.add.assert_not_called()
        mock_uow.ledger.add.assert_not_called()
        mock_uow.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_idempotency_continues_processing(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        valid_command: AuthorizePaymentCommand,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Pending idempotency record continues with payment processing."""
        pending_record = IdempotencyRecord(
            key=valid_command.idempotency_key,
            status="PENDING",
            payment_id=None,
            created_at=datetime.now(UTC),
        )
        mock_uow.idempotency.get.return_value = pending_record
        mock_uow.accounts.get.side_effect = [
            sample_payer_account,
            sample_payee_account,
        ]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        result = await service.authorize_payment(valid_command)

        assert result.status == PaymentStatus.AUTHORIZED
        mock_uow.payments.add.assert_called_once()


class TestPaymentServiceValidation:
    """Tests for payment validation."""

    @pytest.fixture
    def service(self, mock_uow: AsyncMock) -> PaymentService:
        """Create PaymentService with mocked UoW."""
        return PaymentService(mock_uow)

    @pytest.mark.asyncio
    async def test_invalid_amount_zero_declined(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Payment with zero amount is declined."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer",
            payee_account_id="payee",
            amount_cents=0,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.DECLINED
        assert result.error_code == "INVALID_AMOUNT"
        assert result.payment_id == ""

    @pytest.mark.asyncio
    async def test_invalid_amount_negative_declined(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Payment with negative amount is declined."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer",
            payee_account_id="payee",
            amount_cents=-100,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.DECLINED
        assert result.error_code == "INVALID_AMOUNT"

    @pytest.mark.asyncio
    async def test_same_account_declined(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Payment to same account is declined."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="same-account",
            payee_account_id="same-account",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.DECLINED
        assert result.error_code == "SAME_ACCOUNT"

    @pytest.mark.asyncio
    async def test_payer_account_not_found_declined(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Payment with non-existent payer is declined."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="non-existent-payer",
            payee_account_id="payee",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.return_value = None

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.DECLINED
        assert result.error_code == "ACCOUNT_NOT_FOUND"
        assert "non-existent-payer" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_payee_account_not_found_declined(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        sample_payer_account: Account,
    ) -> None:
        """Payment with non-existent payee is declined."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer-account-001",
            payee_account_id="non-existent-payee",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [sample_payer_account, None]

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.DECLINED
        assert result.error_code == "ACCOUNT_NOT_FOUND"
        assert "non-existent-payee" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_insufficient_funds_declined(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        sample_payer_account: Account,
        sample_payee_account: Account,
    ) -> None:
        """Payment declined for insufficient funds."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer-account-001",
            payee_account_id="payee-account-002",
            amount_cents=1000000,  # More than available
            currency="USD",
        )
        low_balance = create_account_balance(
            account_id="payer-account-001",
            available_cents=500,  # Less than required
        )
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [sample_payer_account, sample_payee_account]
        mock_uow.balances.get.return_value = low_balance

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.DECLINED
        assert result.error_code == "INSUFFICIENT_FUNDS"

    @pytest.mark.asyncio
    async def test_no_balance_record_declined(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        sample_payer_account: Account,
        sample_payee_account: Account,
    ) -> None:
        """Payment declined when payer has no balance record."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer-account-001",
            payee_account_id="payee-account-002",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [sample_payer_account, sample_payee_account]
        mock_uow.balances.get.return_value = None

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.DECLINED
        assert result.error_code == "INSUFFICIENT_FUNDS"


class TestPaymentServiceDeclinedPaymentHandling:
    """Tests for handling declined payments."""

    @pytest.fixture
    def service(self, mock_uow: AsyncMock) -> PaymentService:
        """Create PaymentService with mocked UoW."""
        return PaymentService(mock_uow)

    @pytest.mark.asyncio
    async def test_declined_payment_marks_idempotency_failed(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Declined payment marks idempotency as failed."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="same-account",
            payee_account_id="same-account",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None

        await service.authorize_payment(command)

        mock_uow.idempotency.mark_failed.assert_called_once_with("test-key")

    @pytest.mark.asyncio
    async def test_declined_payment_commits_transaction(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Declined payment still commits the transaction."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="same-account",
            payee_account_id="same-account",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None

        await service.authorize_payment(command)

        mock_uow.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_declined_payment_does_not_save_payment(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Declined payment does not save payment record."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="same-account",
            payee_account_id="same-account",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None

        await service.authorize_payment(command)

        mock_uow.payments.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_declined_payment_does_not_create_ledger_entries(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Declined payment does not create ledger entries."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="same-account",
            payee_account_id="same-account",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None

        await service.authorize_payment(command)

        mock_uow.ledger.add.assert_not_called()


class TestPaymentServiceGetPayment:
    """Tests for PaymentService.get_payment."""

    @pytest.fixture
    def service(self, mock_uow: AsyncMock) -> PaymentService:
        """Create PaymentService with mocked UoW."""
        return PaymentService(mock_uow)

    @pytest.mark.asyncio
    async def test_get_payment_found(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Get payment returns payment when found."""
        expected_payment = Payment(
            id="pay-001",
            idempotency_key="key-001",
            payer_account_id="payer",
            payee_account_id="payee",
            amount_cents=1000,
            currency="USD",
            status=PaymentStatus.AUTHORIZED,
        )
        mock_uow.payments.get.return_value = expected_payment

        result = await service.get_payment("pay-001")

        assert result == expected_payment
        mock_uow.payments.get.assert_called_once_with("pay-001")

    @pytest.mark.asyncio
    async def test_get_payment_not_found(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Get payment returns None when not found."""
        mock_uow.payments.get.return_value = None

        result = await service.get_payment("non-existent")

        assert result is None


class TestPaymentServiceGetAccountBalance:
    """Tests for PaymentService.get_account_balance."""

    @pytest.fixture
    def service(self, mock_uow: AsyncMock) -> PaymentService:
        """Create PaymentService with mocked UoW."""
        return PaymentService(mock_uow)

    @pytest.mark.asyncio
    async def test_get_account_balance_found(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        sample_payer_balance: AccountBalance,
    ) -> None:
        """Get account balance returns balance when found."""
        mock_uow.balances.get.return_value = sample_payer_balance

        result = await service.get_account_balance("payer-account-001")

        assert result == sample_payer_balance
        mock_uow.balances.get.assert_called_once_with("payer-account-001")

    @pytest.mark.asyncio
    async def test_get_account_balance_not_found(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Get account balance returns None when not found."""
        mock_uow.balances.get.return_value = None

        result = await service.get_account_balance("non-existent")

        assert result is None


class TestPaymentServiceTransactionBoundary:
    """Tests for transaction boundary behavior."""

    @pytest.fixture
    def service(self, mock_uow: AsyncMock) -> PaymentService:
        """Create PaymentService with mocked UoW."""
        return PaymentService(mock_uow)

    @pytest.mark.asyncio
    async def test_uses_unit_of_work_context_manager(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
    ) -> None:
        """Service uses UoW context manager for transactions."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="same-account",
            payee_account_id="same-account",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None

        await service.authorize_payment(command)

        mock_uow.__aenter__.assert_called_once()
        mock_uow.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_commit_called_only_on_success(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Commit is called after successful authorization."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer-account-001",
            payee_account_id="payee-account-002",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [sample_payer_account, sample_payee_account]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        await service.authorize_payment(command)

        mock_uow.commit.assert_called_once()
        mock_uow.rollback.assert_not_called()


class TestPaymentServiceEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture
    def service(self, mock_uow: AsyncMock) -> PaymentService:
        """Create PaymentService with mocked UoW."""
        return PaymentService(mock_uow)

    @pytest.mark.asyncio
    async def test_exact_balance_payment_succeeds(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Payment with exact available balance succeeds."""
        exact_balance = create_account_balance(
            account_id="payer-account-001",
            available_cents=1000,  # Exact amount
        )
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer-account-001",
            payee_account_id="payee-account-002",
            amount_cents=1000,
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [sample_payer_account, sample_payee_account]
        mock_uow.balances.get.return_value = exact_balance
        mock_uow.balances.get_for_update.side_effect = [
            exact_balance,
            sample_payee_balance,
        ]

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.AUTHORIZED

    @pytest.mark.asyncio
    async def test_large_amount_payment(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Large payment amount is handled correctly."""
        large_balance = create_account_balance(
            account_id="payer-account-001",
            available_cents=10_000_000_00,  # $10 million
        )
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer-account-001",
            payee_account_id="payee-account-002",
            amount_cents=5_000_000_00,  # $5 million
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [sample_payer_account, sample_payee_account]
        mock_uow.balances.get.return_value = large_balance
        mock_uow.balances.get_for_update.side_effect = [
            large_balance,
            sample_payee_balance,
        ]

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.AUTHORIZED

    @pytest.mark.asyncio
    async def test_minimum_amount_payment(
        self,
        service: PaymentService,
        mock_uow: AsyncMock,
        sample_payer_account: Account,
        sample_payee_account: Account,
        sample_payer_balance: AccountBalance,
        sample_payee_balance: AccountBalance,
    ) -> None:
        """Minimum amount (1 cent) payment succeeds."""
        command = AuthorizePaymentCommand(
            idempotency_key="test-key",
            payer_account_id="payer-account-001",
            payee_account_id="payee-account-002",
            amount_cents=1,  # 1 cent
            currency="USD",
        )
        mock_uow.idempotency.get.return_value = None
        mock_uow.accounts.get.side_effect = [sample_payer_account, sample_payee_account]
        mock_uow.balances.get.return_value = sample_payer_balance
        mock_uow.balances.get_for_update.side_effect = [
            sample_payer_balance,
            sample_payee_balance,
        ]

        result = await service.authorize_payment(command)

        assert result.status == PaymentStatus.AUTHORIZED
