"""Shared pytest fixtures for payment service tests."""

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from payment_service.application.unit_of_work import UnitOfWork
from payment_service.domain.models import (
    Account,
    AccountBalance,
    IdempotencyRecord,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_account_repository() -> AsyncMock:
    """Create mock AccountRepository."""
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.add = AsyncMock(return_value=None)
    repo.update_status = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_payment_repository() -> AsyncMock:
    """Create mock PaymentRepository."""
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.get_by_idempotency_key = AsyncMock(return_value=None)
    repo.add = AsyncMock(return_value=None)
    repo.update_status = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_balance_repository() -> AsyncMock:
    """Create mock BalanceRepository."""
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.get_for_update = AsyncMock(return_value=None)
    repo.add = AsyncMock(return_value=None)
    repo.update = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_idempotency_repository() -> AsyncMock:
    """Create mock IdempotencyRepository."""
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=None)
    repo.mark_completed = AsyncMock(return_value=None)
    repo.mark_failed = AsyncMock(return_value=None)
    repo.delete_expired = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_ledger_repository() -> AsyncMock:
    """Create mock LedgerRepository."""
    repo = AsyncMock()
    repo.add = AsyncMock(return_value=None)
    repo.get_by_payment_id = AsyncMock(return_value=[])
    repo.get_by_account_id = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_outbox_repository() -> AsyncMock:
    """Create mock OutboxRepository."""
    repo = AsyncMock()
    repo.add = AsyncMock(return_value=MagicMock())
    repo.get_unpublished = AsyncMock(return_value=[])
    repo.mark_published = AsyncMock(return_value=None)
    repo.increment_retry_count = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_uow(
    mock_account_repository: AsyncMock,
    mock_payment_repository: AsyncMock,
    mock_balance_repository: AsyncMock,
    mock_idempotency_repository: AsyncMock,
    mock_ledger_repository: AsyncMock,
    mock_outbox_repository: AsyncMock,
) -> AsyncMock:
    """Create mock Unit of Work with all repositories."""
    uow = AsyncMock(spec=UnitOfWork)
    uow.accounts = mock_account_repository
    uow.payments = mock_payment_repository
    uow.balances = mock_balance_repository
    uow.idempotency = mock_idempotency_repository
    uow.ledger = mock_ledger_repository
    uow.outbox = mock_outbox_repository
    uow.commit = AsyncMock(return_value=None)
    uow.rollback = AsyncMock(return_value=None)

    # Configure async context manager
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)

    return uow


@pytest.fixture
def sample_payer_account() -> Account:
    """Create sample payer account."""
    return Account(
        id="payer-account-001",
        owner_id="owner-001",
        currency="USD",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_payee_account() -> Account:
    """Create sample payee account."""
    return Account(
        id="payee-account-002",
        owner_id="owner-002",
        currency="USD",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_payer_balance() -> AccountBalance:
    """Create sample payer balance with sufficient funds."""
    return AccountBalance(
        account_id="payer-account-001",
        available_balance_cents=100000,  # $1000.00
        pending_balance_cents=0,
        currency="USD",
        version=1,
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_payee_balance() -> AccountBalance:
    """Create sample payee balance."""
    return AccountBalance(
        account_id="payee-account-002",
        available_balance_cents=50000,  # $500.00
        pending_balance_cents=0,
        currency="USD",
        version=1,
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_idempotency_record() -> IdempotencyRecord:
    """Create sample completed idempotency record."""
    return IdempotencyRecord(
        key="existing-idempotency-key",
        status="COMPLETED",
        payment_id="existing-payment-id-123",
        response_data={"status": "AUTHORIZED"},
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
    )


def create_account_balance(
    account_id: str,
    available_cents: int = 10000,
    pending_cents: int = 0,
    currency: str = "USD",
    version: int = 1,
) -> AccountBalance:
    """Helper to create AccountBalance with custom values."""
    return AccountBalance(
        account_id=account_id,
        available_balance_cents=available_cents,
        pending_balance_cents=pending_cents,
        currency=currency,
        version=version,
        updated_at=datetime.now(UTC),
    )


def create_account(
    account_id: str,
    owner_id: str = "owner-001",
    currency: str = "USD",
    status: str = "ACTIVE",
) -> Account:
    """Helper to create Account with custom values."""
    return Account(
        id=account_id,
        owner_id=owner_id,
        currency=currency,
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
