import grpc
import structlog

from payment_service.application.services import (
    AuthorizePaymentCommand,
    PaymentService,
)
from payment_service.application.unit_of_work import UnitOfWork
from payment_service.domain.models import PaymentStatus
from payment_service.infrastructure.database import Database
from payment_service.proto.payment.v1 import payment_pb2, payment_pb2_grpc


logger = structlog.get_logger()


ERROR_CODE_MAP = {
    "INSUFFICIENT_FUNDS": payment_pb2.PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS,
    "ACCOUNT_NOT_FOUND": payment_pb2.PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND,
    "INVALID_AMOUNT": payment_pb2.PAYMENT_ERROR_CODE_INVALID_AMOUNT,
    "SAME_ACCOUNT": payment_pb2.PAYMENT_ERROR_CODE_SAME_ACCOUNT,
    "CURRENCY_MISMATCH": payment_pb2.PAYMENT_ERROR_CODE_CURRENCY_MISMATCH,
    "RATE_LIMITED": payment_pb2.PAYMENT_ERROR_CODE_RATE_LIMITED,
}

STATUS_MAP = {
    PaymentStatus.AUTHORIZED: payment_pb2.PAYMENT_STATUS_AUTHORIZED,
    PaymentStatus.DECLINED: payment_pb2.PAYMENT_STATUS_DECLINED,
    PaymentStatus.DUPLICATE: payment_pb2.PAYMENT_STATUS_DUPLICATE,
}


class PaymentServiceHandler(payment_pb2_grpc.PaymentServiceServicer):
    def __init__(self, database: Database) -> None:
        self._database = database

    async def AuthorizePayment(
        self,
        request: payment_pb2.AuthorizePaymentRequest,
        context: grpc.aio.ServicerContext,
    ) -> payment_pb2.AuthorizePaymentResponse:
        log = logger.bind(
            method="AuthorizePayment",
            idempotency_key=request.idempotency_key,
        )
        log.info("request_received")

        if not request.idempotency_key:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "idempotency_key is required",
            )

        if not request.payer_account_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "payer_account_id is required",
            )

        if not request.payee_account_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "payee_account_id is required",
            )

        if not request.currency:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "currency is required",
            )

        async with self._database.session() as session:
            uow = UnitOfWork(session)
            payment_service = PaymentService(uow)

            cmd = AuthorizePaymentCommand(
                idempotency_key=request.idempotency_key,
                payer_account_id=request.payer_account_id,
                payee_account_id=request.payee_account_id,
                amount_cents=request.amount_cents,
                currency=request.currency,
                description=request.description or None,
            )

            result = await payment_service.authorize_payment(cmd)

        error = None
        if result.error_code:
            error = payment_pb2.PaymentError(
                code=ERROR_CODE_MAP.get(result.error_code, payment_pb2.PAYMENT_ERROR_CODE_UNSPECIFIED),
                message=result.error_message or "",
            )

        processed_at = ""
        if result.processed_at:
            processed_at = result.processed_at.isoformat()

        return payment_pb2.AuthorizePaymentResponse(
            payment_id=result.payment_id,
            status=STATUS_MAP.get(result.status, payment_pb2.PAYMENT_STATUS_UNSPECIFIED),
            error=error,
            processed_at=processed_at,
        )

    async def GetPayment(
        self,
        request: payment_pb2.GetPaymentRequest,
        context: grpc.aio.ServicerContext,
    ) -> payment_pb2.GetPaymentResponse:
        log = logger.bind(method="GetPayment", payment_id=request.payment_id)
        log.info("request_received")

        if not request.payment_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "payment_id is required",
            )
            raise AssertionError("unreachable")

        async with self._database.session() as session:
            uow = UnitOfWork(session)
            payment_service = PaymentService(uow)
            payment = await payment_service.get_payment(request.payment_id)

        if not payment:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Payment {request.payment_id} not found",
            )
            raise AssertionError("unreachable")

        return payment_pb2.GetPaymentResponse(
            payment=payment_pb2.Payment(
                payment_id=payment.id,
                payer_account_id=payment.payer_account_id,
                payee_account_id=payment.payee_account_id,
                amount_cents=payment.amount_cents,
                currency=payment.currency,
                status=STATUS_MAP.get(payment.status, payment_pb2.PAYMENT_STATUS_UNSPECIFIED),
                description=payment.description or "",
                created_at=payment.created_at.isoformat(),
                updated_at=payment.updated_at.isoformat(),
            )
        )

    async def GetAccountBalance(
        self,
        request: payment_pb2.GetAccountBalanceRequest,
        context: grpc.aio.ServicerContext,
    ) -> payment_pb2.GetAccountBalanceResponse:
        log = logger.bind(method="GetAccountBalance", account_id=request.account_id)
        log.info("request_received")

        if not request.account_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "account_id is required",
            )
            raise AssertionError("unreachable")

        async with self._database.session() as session:
            uow = UnitOfWork(session)
            payment_service = PaymentService(uow)
            balance = await payment_service.get_account_balance(request.account_id)

        if not balance:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Account balance for {request.account_id} not found",
            )
            raise AssertionError("unreachable")

        return payment_pb2.GetAccountBalanceResponse(
            account_id=balance.account_id,
            available_balance_cents=balance.available_balance_cents,
            pending_balance_cents=balance.pending_balance_cents,
            currency=balance.currency,
        )
