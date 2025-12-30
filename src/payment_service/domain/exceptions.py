class DomainError(Exception):
    """Base exception for domain errors."""


class InsufficientFundsError(DomainError):
    """Raised when account has insufficient funds for a transaction."""

    def __init__(self, account_id: str, required: int, available: int) -> None:
        self.account_id = account_id
        self.required = required
        self.available = available
        super().__init__(f"Account {account_id} has insufficient funds: required {required}, available {available}")


class AccountNotFoundError(DomainError):
    """Raised when an account cannot be found."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Account {account_id} not found")


class InvalidAmountError(DomainError):
    """Raised when payment amount is invalid."""

    def __init__(self, amount: int, reason: str) -> None:
        self.amount = amount
        self.reason = reason
        super().__init__(f"Invalid amount {amount}: {reason}")


class SameAccountError(DomainError):
    """Raised when payer and payee are the same account."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Cannot transfer to the same account: {account_id}")


class OptimisticLockError(DomainError):
    """Raised when optimistic locking conflict occurs."""

    def __init__(self, entity: str, entity_id: str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"Optimistic lock failed for {entity} {entity_id}")


class CurrencyMismatchError(DomainError):
    """Raised when currencies don't match."""

    def __init__(self, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"Currency mismatch: expected {expected}, got {actual}")
