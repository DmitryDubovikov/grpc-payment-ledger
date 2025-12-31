"""End-to-end tests for complete payment flow.

These tests require running services (gRPC server, PostgreSQL, Redis, Redpanda).
Run with: pytest tests/e2e -v --e2e
"""

import asyncio
from uuid import uuid4

import grpc
import pytest

from payment_service.proto.payment.v1 import payment_pb2, payment_pb2_grpc


pytestmark = pytest.mark.e2e


@pytest.fixture
async def grpc_channel() -> grpc.aio.Channel:
    """Connect to running gRPC service."""
    channel = grpc.aio.insecure_channel("localhost:50051")
    try:
        await asyncio.wait_for(
            channel.channel_ready(),
            timeout=10,
        )
    except TimeoutError:
        pytest.skip("gRPC server not available at localhost:50051")
    yield channel
    await channel.close()


@pytest.fixture
def payment_stub(grpc_channel: grpc.aio.Channel) -> payment_pb2_grpc.PaymentServiceStub:
    """Create PaymentService stub."""
    return payment_pb2_grpc.PaymentServiceStub(grpc_channel)


class TestPaymentFlow:
    """End-to-end tests for complete payment flow."""

    async def test_complete_payment_flow(
        self,
        payment_stub: payment_pb2_grpc.PaymentServiceStub,
    ) -> None:
        """
        Test complete flow:
        1. Check initial balances
        2. Authorize payment
        3. Verify balances updated
        4. Verify idempotency works
        5. Verify payment details
        """
        payer_id = "test-payer-001"
        payee_id = "test-payee-001"

        payer_balance = await payment_stub.GetAccountBalance(payment_pb2.GetAccountBalanceRequest(account_id=payer_id))
        initial_payer_balance = payer_balance.available_balance_cents

        payee_balance = await payment_stub.GetAccountBalance(payment_pb2.GetAccountBalanceRequest(account_id=payee_id))
        initial_payee_balance = payee_balance.available_balance_cents

        idempotency_key = str(uuid4())
        amount = 5000

        response = await payment_stub.AuthorizePayment(
            payment_pb2.AuthorizePaymentRequest(
                idempotency_key=idempotency_key,
                payer_account_id=payer_id,
                payee_account_id=payee_id,
                amount_cents=amount,
                currency="USD",
                description="E2E test payment",
            )
        )

        assert response.status == payment_pb2.PAYMENT_STATUS_AUTHORIZED
        payment_id = response.payment_id
        assert len(payment_id) == 26

        payer_balance = await payment_stub.GetAccountBalance(payment_pb2.GetAccountBalanceRequest(account_id=payer_id))
        assert payer_balance.available_balance_cents == initial_payer_balance - amount

        payee_balance = await payment_stub.GetAccountBalance(payment_pb2.GetAccountBalanceRequest(account_id=payee_id))
        assert payee_balance.available_balance_cents == initial_payee_balance + amount

        duplicate_response = await payment_stub.AuthorizePayment(
            payment_pb2.AuthorizePaymentRequest(
                idempotency_key=idempotency_key,
                payer_account_id=payer_id,
                payee_account_id=payee_id,
                amount_cents=amount,
                currency="USD",
            )
        )

        assert duplicate_response.status == payment_pb2.PAYMENT_STATUS_DUPLICATE
        assert duplicate_response.payment_id == payment_id

        payment = await payment_stub.GetPayment(payment_pb2.GetPaymentRequest(payment_id=payment_id))

        assert payment.payment.amount_cents == amount
        assert payment.payment.payer_account_id == payer_id
        assert payment.payment.payee_account_id == payee_id

    async def test_insufficient_funds_declined(
        self,
        payment_stub: payment_pb2_grpc.PaymentServiceStub,
    ) -> None:
        """Test payment declined for insufficient funds."""
        payer_id = "test-payer-001"
        payee_id = "test-payee-001"

        response = await payment_stub.AuthorizePayment(
            payment_pb2.AuthorizePaymentRequest(
                idempotency_key=str(uuid4()),
                payer_account_id=payer_id,
                payee_account_id=payee_id,
                amount_cents=999999999,
                currency="USD",
            )
        )

        assert response.status == payment_pb2.PAYMENT_STATUS_DECLINED
        assert response.error.code == payment_pb2.PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS

    async def test_concurrent_payments_no_overdraft(
        self,
        payment_stub: payment_pb2_grpc.PaymentServiceStub,
    ) -> None:
        """Test concurrent payments don't cause overdraft."""
        payer_id = "test-payer-001"
        payee_id = "test-payee-001"

        balance = await payment_stub.GetAccountBalance(payment_pb2.GetAccountBalanceRequest(account_id=payer_id))
        available = balance.available_balance_cents

        payment_amount = available // 2 + 100

        async def make_payment() -> payment_pb2.AuthorizePaymentResponse:
            return await payment_stub.AuthorizePayment(
                payment_pb2.AuthorizePaymentRequest(
                    idempotency_key=str(uuid4()),
                    payer_account_id=payer_id,
                    payee_account_id=payee_id,
                    amount_cents=payment_amount,
                    currency="USD",
                )
            )

        results = await asyncio.gather(*[make_payment() for _ in range(5)])

        authorized = sum(1 for r in results if r.status == payment_pb2.PAYMENT_STATUS_AUTHORIZED)
        declined = sum(1 for r in results if r.status == payment_pb2.PAYMENT_STATUS_DECLINED)

        assert authorized == 1
        assert declined == 4

        final_balance = await payment_stub.GetAccountBalance(payment_pb2.GetAccountBalanceRequest(account_id=payer_id))
        assert final_balance.available_balance_cents >= 0

    async def test_same_account_transfer_declined(
        self,
        payment_stub: payment_pb2_grpc.PaymentServiceStub,
    ) -> None:
        """Test that transferring to the same account is declined."""
        account_id = "test-payer-001"

        response = await payment_stub.AuthorizePayment(
            payment_pb2.AuthorizePaymentRequest(
                idempotency_key=str(uuid4()),
                payer_account_id=account_id,
                payee_account_id=account_id,
                amount_cents=1000,
                currency="USD",
            )
        )

        assert response.status == payment_pb2.PAYMENT_STATUS_DECLINED
        assert response.error.code == payment_pb2.PAYMENT_ERROR_CODE_SAME_ACCOUNT

    async def test_invalid_amount_declined(
        self,
        payment_stub: payment_pb2_grpc.PaymentServiceStub,
    ) -> None:
        """Test that zero or negative amount is declined."""
        response = await payment_stub.AuthorizePayment(
            payment_pb2.AuthorizePaymentRequest(
                idempotency_key=str(uuid4()),
                payer_account_id="test-payer-001",
                payee_account_id="test-payee-001",
                amount_cents=0,
                currency="USD",
            )
        )

        assert response.status == payment_pb2.PAYMENT_STATUS_DECLINED
        assert response.error.code == payment_pb2.PAYMENT_ERROR_CODE_INVALID_AMOUNT

    async def test_account_not_found_declined(
        self,
        payment_stub: payment_pb2_grpc.PaymentServiceStub,
    ) -> None:
        """Test that non-existent account is declined."""
        response = await payment_stub.AuthorizePayment(
            payment_pb2.AuthorizePaymentRequest(
                idempotency_key=str(uuid4()),
                payer_account_id="nonexistent-payer",
                payee_account_id="test-payee-001",
                amount_cents=1000,
                currency="USD",
            )
        )

        assert response.status == payment_pb2.PAYMENT_STATUS_DECLINED
        assert response.error.code == payment_pb2.PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND


class TestHealthCheck:
    """Tests for gRPC health checks."""

    async def test_health_check_serving(
        self,
        grpc_channel: grpc.aio.Channel,
    ) -> None:
        """Test that health check returns SERVING."""
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        stub = health_pb2_grpc.HealthStub(grpc_channel)
        response = await stub.Check(health_pb2.HealthCheckRequest())

        assert response.status == health_pb2.HealthCheckResponse.SERVING

    async def test_payment_service_health(
        self,
        grpc_channel: grpc.aio.Channel,
    ) -> None:
        """Test that payment service health check returns SERVING."""
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        stub = health_pb2_grpc.HealthStub(grpc_channel)
        response = await stub.Check(health_pb2.HealthCheckRequest(service="payment.v1.PaymentService"))

        assert response.status == health_pb2.HealthCheckResponse.SERVING


class TestReflection:
    """Tests for gRPC reflection."""

    async def test_list_services(
        self,
        grpc_channel: grpc.aio.Channel,
    ) -> None:
        """Test that reflection lists available services."""
        from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc

        stub = reflection_pb2_grpc.ServerReflectionStub(grpc_channel)

        async def get_services() -> list[str]:
            request = reflection_pb2.ServerReflectionRequest(list_services="")

            async def request_gen():
                yield request

            responses = stub.ServerReflectionInfo(request_gen())
            services = []
            async for response in responses:
                if response.HasField("list_services_response"):
                    for service in response.list_services_response.service:
                        services.append(service.name)
            return services

        services = await get_services()

        assert "payment.v1.PaymentService" in services
        assert "grpc.health.v1.Health" in services
        assert "grpc.reflection.v1alpha.ServerReflection" in services
