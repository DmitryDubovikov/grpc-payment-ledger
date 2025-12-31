# ===== BUILD STAGE =====
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code
COPY src/ src/
COPY proto/ proto/
COPY scripts/ scripts/
COPY alembic/ alembic/
COPY alembic.ini ./

# Generate protobuf files and fix import paths
RUN mkdir -p src/payment_service/proto/payment/v1 && \
    touch src/payment_service/proto/__init__.py && \
    touch src/payment_service/proto/payment/__init__.py && \
    touch src/payment_service/proto/payment/v1/__init__.py && \
    uv run python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=src/payment_service/proto \
    --pyi_out=src/payment_service/proto \
    --grpc_python_out=src/payment_service/proto \
    proto/payment/v1/payment.proto && \
    find src/payment_service/proto -name "*.py" -exec sed -i 's/^from payment\./from payment_service.proto.payment./' {} \;

# ===== RUNTIME BASE =====
FROM python:3.12-slim AS runtime-base

# Security: create non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy uv and virtual environment from builder (with correct ownership)
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/src /app/src
COPY --from=builder --chown=appuser:appgroup /app/scripts /app/scripts
COPY --from=builder --chown=appuser:appgroup /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appgroup /app/alembic.ini /app/alembic.ini

# Set environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# ===== GRPC SERVER =====
FROM runtime-base AS runtime

# Health check for gRPC server
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; ch = grpc.insecure_channel('localhost:50051'); grpc.channel_ready_future(ch).result(timeout=5)" || exit 1

EXPOSE 50051

CMD ["python", "-m", "payment_service.main"]

# ===== OUTBOX PROCESSOR =====
FROM runtime-base AS outbox-processor

# No health check needed for background worker

CMD ["python", "scripts/run_outbox_processor.py"]
