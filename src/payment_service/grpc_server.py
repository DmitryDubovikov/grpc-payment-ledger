import grpc
import structlog
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

from payment_service.api.grpc_handlers import PaymentServiceHandler
from payment_service.infrastructure.database import Database
from payment_service.proto.payment.v1 import payment_pb2, payment_pb2_grpc


logger = structlog.get_logger()


class GrpcServer:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._server: grpc.aio.Server | None = None
        self._health_servicer = health.HealthServicer()

    async def start(self, port: int = 50051) -> None:
        self._server = grpc.aio.server(
            options=[
                ("grpc.max_send_message_length", 50 * 1024 * 1024),
                ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ]
        )

        payment_handler = PaymentServiceHandler(self._database)
        payment_pb2_grpc.add_PaymentServiceServicer_to_server(payment_handler, self._server)

        health_pb2_grpc.add_HealthServicer_to_server(self._health_servicer, self._server)

        service_names = (
            payment_pb2.DESCRIPTOR.services_by_name["PaymentService"].full_name,
            health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(service_names, self._server)

        self._health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
        self._health_servicer.set(
            "payment.v1.PaymentService",
            health_pb2.HealthCheckResponse.SERVING,
        )

        listen_addr = f"[::]:{port}"
        self._server.add_insecure_port(listen_addr)

        await self._server.start()
        logger.info("grpc_server_started", port=port)

    async def wait_for_termination(self) -> None:
        if self._server:
            await self._server.wait_for_termination()

    async def stop(self, grace: float = 10.0) -> None:
        if self._server:
            self._health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
            await self._server.stop(grace)
            logger.info("grpc_server_stopped")
