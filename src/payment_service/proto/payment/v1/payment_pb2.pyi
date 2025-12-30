from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class PaymentStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PAYMENT_STATUS_UNSPECIFIED: _ClassVar[PaymentStatus]
    PAYMENT_STATUS_AUTHORIZED: _ClassVar[PaymentStatus]
    PAYMENT_STATUS_DECLINED: _ClassVar[PaymentStatus]
    PAYMENT_STATUS_DUPLICATE: _ClassVar[PaymentStatus]

class PaymentErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PAYMENT_ERROR_CODE_UNSPECIFIED: _ClassVar[PaymentErrorCode]
    PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS: _ClassVar[PaymentErrorCode]
    PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND: _ClassVar[PaymentErrorCode]
    PAYMENT_ERROR_CODE_INVALID_AMOUNT: _ClassVar[PaymentErrorCode]
    PAYMENT_ERROR_CODE_SAME_ACCOUNT: _ClassVar[PaymentErrorCode]
    PAYMENT_ERROR_CODE_CURRENCY_MISMATCH: _ClassVar[PaymentErrorCode]
    PAYMENT_ERROR_CODE_RATE_LIMITED: _ClassVar[PaymentErrorCode]

PAYMENT_STATUS_UNSPECIFIED: PaymentStatus
PAYMENT_STATUS_AUTHORIZED: PaymentStatus
PAYMENT_STATUS_DECLINED: PaymentStatus
PAYMENT_STATUS_DUPLICATE: PaymentStatus
PAYMENT_ERROR_CODE_UNSPECIFIED: PaymentErrorCode
PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS: PaymentErrorCode
PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND: PaymentErrorCode
PAYMENT_ERROR_CODE_INVALID_AMOUNT: PaymentErrorCode
PAYMENT_ERROR_CODE_SAME_ACCOUNT: PaymentErrorCode
PAYMENT_ERROR_CODE_CURRENCY_MISMATCH: PaymentErrorCode
PAYMENT_ERROR_CODE_RATE_LIMITED: PaymentErrorCode

class AuthorizePaymentRequest(_message.Message):
    __slots__ = ("amount_cents", "currency", "description", "idempotency_key", "payee_account_id", "payer_account_id")
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    PAYER_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    PAYEE_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    idempotency_key: str
    payer_account_id: str
    payee_account_id: str
    amount_cents: int
    currency: str
    description: str
    def __init__(
        self,
        idempotency_key: str | None = ...,
        payer_account_id: str | None = ...,
        payee_account_id: str | None = ...,
        amount_cents: int | None = ...,
        currency: str | None = ...,
        description: str | None = ...,
    ) -> None: ...

class AuthorizePaymentResponse(_message.Message):
    __slots__ = ("error", "payment_id", "processed_at", "status")
    PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    PROCESSED_AT_FIELD_NUMBER: _ClassVar[int]
    payment_id: str
    status: PaymentStatus
    error: PaymentError
    processed_at: str
    def __init__(
        self,
        payment_id: str | None = ...,
        status: PaymentStatus | str | None = ...,
        error: PaymentError | _Mapping | None = ...,
        processed_at: str | None = ...,
    ) -> None: ...

class GetPaymentRequest(_message.Message):
    __slots__ = ("payment_id",)
    PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    payment_id: str
    def __init__(self, payment_id: str | None = ...) -> None: ...

class GetPaymentResponse(_message.Message):
    __slots__ = ("payment",)
    PAYMENT_FIELD_NUMBER: _ClassVar[int]
    payment: Payment
    def __init__(self, payment: Payment | _Mapping | None = ...) -> None: ...

class GetAccountBalanceRequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    def __init__(self, account_id: str | None = ...) -> None: ...

class GetAccountBalanceResponse(_message.Message):
    __slots__ = ("account_id", "available_balance_cents", "currency", "pending_balance_cents")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PENDING_BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    available_balance_cents: int
    pending_balance_cents: int
    currency: str
    def __init__(
        self,
        account_id: str | None = ...,
        available_balance_cents: int | None = ...,
        pending_balance_cents: int | None = ...,
        currency: str | None = ...,
    ) -> None: ...

class Payment(_message.Message):
    __slots__ = (
        "amount_cents",
        "created_at",
        "currency",
        "description",
        "payee_account_id",
        "payer_account_id",
        "payment_id",
        "status",
        "updated_at",
    )
    PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    PAYER_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    PAYEE_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    payment_id: str
    payer_account_id: str
    payee_account_id: str
    amount_cents: int
    currency: str
    status: PaymentStatus
    description: str
    created_at: str
    updated_at: str
    def __init__(
        self,
        payment_id: str | None = ...,
        payer_account_id: str | None = ...,
        payee_account_id: str | None = ...,
        amount_cents: int | None = ...,
        currency: str | None = ...,
        status: PaymentStatus | str | None = ...,
        description: str | None = ...,
        created_at: str | None = ...,
        updated_at: str | None = ...,
    ) -> None: ...

class PaymentError(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: PaymentErrorCode
    message: str
    def __init__(self, code: PaymentErrorCode | str | None = ..., message: str | None = ...) -> None: ...
