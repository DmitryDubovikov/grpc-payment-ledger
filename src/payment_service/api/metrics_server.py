import asyncio
import contextlib

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


logger = structlog.get_logger()


def create_metrics_app() -> FastAPI:
    """Create FastAPI application for metrics endpoint."""
    app = FastAPI(
        title="Payment Service Metrics",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> PlainTextResponse:
        """Prometheus metrics endpoint."""
        return PlainTextResponse(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint for the metrics server."""
        return {"status": "healthy"}

    return app


class MetricsServer:
    """Async metrics server using uvicorn."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9090) -> None:
        self._host = host
        self._port = port
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the metrics server in the background."""
        app = create_metrics_app()
        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        self._task = asyncio.create_task(self._server.serve())
        logger.info("metrics_server_started", host=self._host, port=self._port)

    async def stop(self) -> None:
        """Stop the metrics server."""
        if self._server:
            self._server.should_exit = True

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task

        logger.info("metrics_server_stopped")
