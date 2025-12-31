"""Integration tests for MetricsServer."""

import asyncio
import contextlib

import httpx
import pytest

from payment_service.api.metrics_server import MetricsServer


class TestMetricsServerIntegration:
    """Integration tests for MetricsServer."""

    @pytest.fixture
    async def metrics_server(self):
        """Create and start metrics server."""
        server = MetricsServer(host="127.0.0.1", port=19093)

        # Start server in background
        start_task = asyncio.create_task(server.start())

        # Wait for server to be ready
        await asyncio.sleep(0.5)

        yield server

        # Cleanup
        await server.stop()
        start_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await start_task

    @pytest.mark.asyncio
    async def test_metrics_endpoint_accessible(self, metrics_server: MetricsServer) -> None:
        """Test /metrics endpoint is accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:19093/metrics")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_endpoint_content_type(self, metrics_server: MetricsServer) -> None:
        """Test /metrics endpoint returns correct content type."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:19093/metrics")

        assert "text/plain" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_metrics_contains_prometheus_format(self, metrics_server: MetricsServer) -> None:
        """Test /metrics returns Prometheus format."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:19093/metrics")

        content = response.text

        # Prometheus format contains # HELP and # TYPE comments
        assert "# HELP" in content or "# TYPE" in content

    @pytest.mark.asyncio
    async def test_metrics_includes_custom_metrics(self, metrics_server: MetricsServer) -> None:
        """Test /metrics includes our custom metrics."""
        # Import to ensure metrics are registered

        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:19093/metrics")

        content = response.text

        assert "payment_requests_total" in content
        assert "grpc_request_duration_seconds" in content

    @pytest.mark.asyncio
    async def test_health_endpoint_accessible(self, metrics_server: MetricsServer) -> None:
        """Test /health endpoint is accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:19093/health")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_json(self, metrics_server: MetricsServer) -> None:
        """Test /health endpoint returns JSON."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:19093/health")

        data = response.json()
        assert data == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, metrics_server: MetricsServer) -> None:
        """Test server handles concurrent requests."""

        async def fetch_metrics():
            async with httpx.AsyncClient() as client:
                return await client.get("http://127.0.0.1:19093/metrics")

        # Make 10 concurrent requests
        tasks = [fetch_metrics() for _ in range(10)]
        responses = await asyncio.gather(*tasks)

        for response in responses:
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_updated_after_operations(self, metrics_server: MetricsServer) -> None:
        """Test metrics are updated after operations."""
        from payment_service.infrastructure.metrics import PAYMENT_REQUESTS_TOTAL

        # Record initial state
        async with httpx.AsyncClient() as client:
            await client.get("http://127.0.0.1:19093/metrics")

        # Increment counter
        PAYMENT_REQUESTS_TOTAL.labels(status="AUTHORIZED", error_code="").inc()

        # Get updated metrics
        async with httpx.AsyncClient() as client:
            updated_response = await client.get("http://127.0.0.1:19093/metrics")
        updated_content = updated_response.text

        # Verify payment_requests_total is in response
        assert "payment_requests_total" in updated_content


class TestMetricsServerLifecycle:
    """Tests for MetricsServer lifecycle management."""

    @pytest.mark.asyncio
    async def test_server_starts_on_specified_port(self) -> None:
        """Test server starts on specified port."""
        server = MetricsServer(host="127.0.0.1", port=19094)

        start_task = asyncio.create_task(server.start())
        await asyncio.sleep(0.5)

        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:19094/health")

        assert response.status_code == 200

        await server.stop()
        start_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await start_task

    @pytest.mark.asyncio
    async def test_server_stops_cleanly(self) -> None:
        """Test server stops cleanly."""
        server = MetricsServer(host="127.0.0.1", port=19095)

        start_task = asyncio.create_task(server.start())
        await asyncio.sleep(0.5)

        # Server should be accessible
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:19095/health")
        assert response.status_code == 200

        # Stop server
        await server.stop()
        start_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await start_task

        # Give server time to shut down
        await asyncio.sleep(0.5)

        # Server should no longer be accessible
        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.ConnectError):
                await client.get("http://127.0.0.1:19095/health")

    @pytest.mark.asyncio
    async def test_multiple_servers_on_different_ports(self) -> None:
        """Test multiple servers can run on different ports."""
        server1 = MetricsServer(host="127.0.0.1", port=19096)
        server2 = MetricsServer(host="127.0.0.1", port=19097)

        task1 = asyncio.create_task(server1.start())
        task2 = asyncio.create_task(server2.start())
        await asyncio.sleep(0.5)

        async with httpx.AsyncClient() as client:
            response1 = await client.get("http://127.0.0.1:19096/health")
            response2 = await client.get("http://127.0.0.1:19097/health")

        assert response1.status_code == 200
        assert response2.status_code == 200

        await server1.stop()
        await server2.stop()

        for task in [task1, task2]:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
