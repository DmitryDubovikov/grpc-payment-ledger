"""Unit tests for MetricsServer."""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from payment_service.api.metrics_server import MetricsServer, create_metrics_app


class TestCreateMetricsApp:
    """Tests for create_metrics_app factory function."""

    def test_creates_fastapi_app(self) -> None:
        """Test factory creates FastAPI application."""
        app = create_metrics_app()

        assert app.title == "Payment Service Metrics"

    def test_disables_docs(self) -> None:
        """Test factory disables documentation endpoints."""
        app = create_metrics_app()

        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    def test_has_metrics_endpoint(self) -> None:
        """Test app has /metrics endpoint."""
        app = create_metrics_app()

        routes = [route.path for route in app.routes]
        assert "/metrics" in routes

    def test_has_health_endpoint(self) -> None:
        """Test app has /health endpoint."""
        app = create_metrics_app()

        routes = [route.path for route in app.routes]
        assert "/health" in routes


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    @pytest.fixture
    def app(self):
        """Create metrics app."""
        return create_metrics_app()

    @pytest.mark.asyncio
    async def test_metrics_returns_prometheus_format(self, app) -> None:
        """Test /metrics returns Prometheus format."""
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_metrics_includes_process_metrics(self, app) -> None:
        """Test /metrics includes process metrics."""
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/metrics")

        # Prometheus client automatically includes process metrics
        assert "process_" in response.text or "python_" in response.text

    @pytest.mark.asyncio
    async def test_metrics_includes_custom_metrics(self, app) -> None:
        """Test /metrics includes custom payment metrics."""
        from fastapi.testclient import TestClient

        # Import to register metrics
        from payment_service.infrastructure import metrics  # noqa: F401

        client = TestClient(app)
        response = client.get("/metrics")

        # Check for our custom metrics
        assert "payment_requests_total" in response.text
        assert "grpc_request_duration_seconds" in response.text


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.fixture
    def app(self):
        """Create metrics app."""
        return create_metrics_app()

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self, app) -> None:
        """Test /health returns healthy status."""
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestMetricsServer:
    """Tests for MetricsServer class."""

    def test_init_with_default_values(self) -> None:
        """Test MetricsServer initializes with default values."""
        server = MetricsServer()

        assert server._host == "0.0.0.0"
        assert server._port == 9090

    def test_init_with_custom_values(self) -> None:
        """Test MetricsServer initializes with custom values."""
        server = MetricsServer(host="127.0.0.1", port=8080)

        assert server._host == "127.0.0.1"
        assert server._port == 8080

    @pytest.mark.asyncio
    async def test_start_creates_server(self) -> None:
        """Test start creates uvicorn server."""
        server = MetricsServer(host="127.0.0.1", port=19090)

        with patch("payment_service.api.metrics_server.uvicorn.Server") as mock_server_class:
            mock_server = MagicMock()
            mock_server.serve = AsyncMock()
            mock_server_class.return_value = mock_server

            with patch("payment_service.api.metrics_server.uvicorn.Config") as mock_config:
                # Start server in background
                task = asyncio.create_task(server.start())

                # Give it a moment to start
                await asyncio.sleep(0.1)

                # Verify server was created
                mock_config.assert_called_once()
                config_kwargs = mock_config.call_args.kwargs
                assert config_kwargs["host"] == "127.0.0.1"
                assert config_kwargs["port"] == 19090
                assert config_kwargs["log_level"] == "warning"
                assert config_kwargs["access_log"] is False

                # Clean up
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    @pytest.mark.asyncio
    async def test_start_logs_info(self) -> None:
        """Test start logs server info."""
        server = MetricsServer(host="127.0.0.1", port=19091)

        with patch("payment_service.api.metrics_server.uvicorn.Server") as mock_server_class:
            mock_server = MagicMock()
            mock_server.serve = AsyncMock()
            mock_server_class.return_value = mock_server

            with patch("payment_service.api.metrics_server.logger") as mock_logger:
                task = asyncio.create_task(server.start())
                await asyncio.sleep(0.1)

                mock_logger.info.assert_called_once_with(
                    "metrics_server_started",
                    host="127.0.0.1",
                    port=19091,
                )

                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self) -> None:
        """Test stop does nothing when not started."""
        server = MetricsServer()

        # Should not raise
        await server.stop()

    @pytest.mark.asyncio
    async def test_stop_sets_should_exit(self) -> None:
        """Test stop sets should_exit on server."""
        server = MetricsServer()

        mock_uvicorn_server = MagicMock()
        mock_task = MagicMock()
        mock_task.__await__ = lambda self: iter([])

        server._server = mock_uvicorn_server
        server._task = asyncio.create_task(asyncio.sleep(10))

        await server.stop()

        assert mock_uvicorn_server.should_exit is True

    @pytest.mark.asyncio
    async def test_stop_waits_for_task(self) -> None:
        """Test stop waits for task to complete."""
        server = MetricsServer()

        completed = False

        async def slow_task():
            nonlocal completed
            await asyncio.sleep(0.1)
            completed = True

        mock_uvicorn_server = MagicMock()
        server._server = mock_uvicorn_server
        server._task = asyncio.create_task(slow_task())

        await server.stop()

        assert completed is True

    @pytest.mark.asyncio
    async def test_stop_cancels_on_timeout(self) -> None:
        """Test stop cancels task on timeout."""
        server = MetricsServer()

        async def infinite_task():
            await asyncio.sleep(100)

        mock_uvicorn_server = MagicMock()
        server._server = mock_uvicorn_server
        server._task = asyncio.create_task(infinite_task())

        # Should not hang due to timeout
        await server.stop()

        assert server._task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_logs_info(self) -> None:
        """Test stop logs server info."""
        server = MetricsServer()

        with patch("payment_service.api.metrics_server.logger") as mock_logger:
            await server.stop()

            mock_logger.info.assert_called_once_with("metrics_server_stopped")


class TestMetricsServerLifecycle:
    """Integration tests for MetricsServer lifecycle."""

    @pytest.mark.asyncio
    async def test_start_stop_cycle(self) -> None:
        """Test complete start/stop cycle."""
        server = MetricsServer(host="127.0.0.1", port=19092)

        with patch("payment_service.api.metrics_server.uvicorn.Server") as mock_server_class:
            mock_uvicorn_server = MagicMock()

            async def mock_serve():
                while not mock_uvicorn_server.should_exit:
                    await asyncio.sleep(0.01)

            mock_uvicorn_server.serve = mock_serve
            mock_uvicorn_server.should_exit = False
            mock_server_class.return_value = mock_uvicorn_server

            # Start server
            start_task = asyncio.create_task(server.start())
            await asyncio.sleep(0.1)

            assert server._server is not None
            assert server._task is not None

            # Stop server
            await server.stop()

            # Verify cleanup
            assert mock_uvicorn_server.should_exit is True

            # Cancel start task
            start_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await start_task

    @pytest.mark.asyncio
    async def test_multiple_stop_calls(self) -> None:
        """Test multiple stop calls are safe."""
        server = MetricsServer()

        # Multiple stops should not raise
        await server.stop()
        await server.stop()
        await server.stop()
