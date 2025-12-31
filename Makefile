.PHONY: help install install-dev format lint lint-fix type-check test test-unit test-integration test-e2e test-cov proto clean docker-build docker-up docker-down db-migrate db-upgrade db-downgrade run up dev-up dev-down migrate grpc-list grpc-health grpc-describe run-outbox-processor run-sample-consumer outbox-logs kafka-topics kafka-consume load-test metrics-check

# Default target
help:
	@echo "Available commands:"
	@echo ""
	@echo "  Development:"
	@echo "    make install        Install production dependencies"
	@echo "    make install-dev    Install all dependencies (including dev)"
	@echo "    make format         Format code with ruff"
	@echo "    make lint           Run linting checks"
	@echo "    make lint-fix       Fix linting issues automatically"
	@echo "    make type-check     Run mypy type checking"
	@echo ""
	@echo "  Testing:"
	@echo "    make test           Run all tests"
	@echo "    make test-unit      Run unit tests only"
	@echo "    make test-integration  Run integration tests"
	@echo "    make test-e2e       Run end-to-end tests"
	@echo "    make test-cov       Run tests with coverage report"
	@echo ""
	@echo "  Proto:"
	@echo "    make proto          Generate protobuf files"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-build   Build Docker images"
	@echo "    make docker-up      Start all services"
	@echo "    make docker-down    Stop all services"
	@echo ""
	@echo "  Database:"
	@echo "    make db-migrate     Create new migration"
	@echo "    make db-upgrade     Apply all migrations"
	@echo "    make db-downgrade   Rollback last migration"
	@echo ""
	@echo "  Event Streaming:"
	@echo "    make run-outbox-processor  Run outbox processor locally"
	@echo "    make run-sample-consumer   Run sample event consumer locally"
	@echo "    make outbox-logs           View outbox processor logs"
	@echo "    make kafka-topics          List Kafka/Redpanda topics"
	@echo "    make kafka-create-topics   Create required topics"
	@echo "    make kafka-consume         Consume payment events"
	@echo "    make kafka-consume-dlq     Consume dead letter queue events"
	@echo ""
	@echo "  Production Readiness:"
	@echo "    make load-test             Run k6 load tests"
	@echo "    make metrics-check         Check Prometheus metrics endpoint"
	@echo ""
	@echo "  Misc:"
	@echo "    make clean          Remove generated files and caches"
	@echo "    make check          Run all checks (format, lint, type-check, test)"

# =============================================================================
# Development
# =============================================================================

install:
	uv sync --frozen --no-dev

install-dev:
	uv sync --frozen

# Format code with ruff
format:
	uv run ruff format src tests

# Run linting checks
lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

# Fix linting issues automatically
lint-fix:
	uv run ruff check --fix src tests
	uv run ruff format src tests

# Type checking with mypy
type-check:
	uv run mypy src

# Run all checks
check: lint type-check test-unit

# =============================================================================
# Testing
# =============================================================================

# PYTHONPATH is required because the package is not installed in editable mode
PYTHONPATH := PYTHONPATH=$(CURDIR)/src

test:
	$(PYTHONPATH) uv run pytest tests -v

test-unit:
	$(PYTHONPATH) uv run pytest tests/unit -v

test-integration:
	$(PYTHONPATH) uv run pytest tests/integration -v

test-e2e:
	$(PYTHONPATH) uv run pytest tests/e2e -v --e2e

test-cov:
	$(PYTHONPATH) uv run pytest tests --cov=src/payment_service --cov-report=html --cov-report=term-missing

# =============================================================================
# Protobuf
# =============================================================================

PROTO_DIR := proto
PROTO_OUT := src/payment_service/proto

proto:
	@mkdir -p $(PROTO_OUT)/payment/v1
	uv run python -m grpc_tools.protoc \
		--proto_path=$(PROTO_DIR) \
		--python_out=$(PROTO_OUT) \
		--grpc_python_out=$(PROTO_OUT) \
		--pyi_out=$(PROTO_OUT) \
		$(PROTO_DIR)/payment/v1/payment.proto
	@# Fix imports in generated files
	@find $(PROTO_OUT) -name "*.py" -exec sed -i '' 's/^from payment/from payment_service.proto.payment/' {} \; 2>/dev/null || \
		find $(PROTO_OUT) -name "*.py" -exec sed -i 's/^from payment/from payment_service.proto.payment/' {} \;
	@touch $(PROTO_OUT)/__init__.py
	@touch $(PROTO_OUT)/payment/__init__.py
	@touch $(PROTO_OUT)/payment/v1/__init__.py
	@echo "Protobuf files generated successfully"

# =============================================================================
# Docker
# =============================================================================

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-ps:
	docker-compose ps

# =============================================================================
# Database
# =============================================================================

# Create new migration: make db-migrate MSG="add users table"
db-migrate:
	uv run alembic revision --autogenerate -m "$(MSG)"

db-upgrade:
	uv run alembic upgrade head

db-downgrade:
	uv run alembic downgrade -1

db-history:
	uv run alembic history

db-current:
	uv run alembic current

# =============================================================================
# Misc
# =============================================================================

clean:
	@rm -rf .pytest_cache
	@rm -rf .mypy_cache
	@rm -rf .ruff_cache
	@rm -rf htmlcov
	@rm -rf .coverage
	@rm -rf dist
	@rm -rf *.egg-info
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned up generated files and caches"

# Run the gRPC server locally
run:
	uv run python -m payment_service.main

# Quick aliases
up: docker-up
	@echo "Services started. Run 'make migrate' to apply migrations."

dev-up: docker-up
	@echo "Services started. Run 'make migrate' to apply migrations."

dev-down: docker-down

migrate: db-upgrade

# Initialize test data for manual testing
init-test-data:
	docker compose exec -T postgres psql -U payment -d payment_db < scripts/init_test_data.sql

# Reset all test data (truncate tables and re-initialize)
reset-test-data:
	docker compose exec -T postgres psql -U payment -d payment_db < scripts/reset_test_data.sql

# gRPC utilities (via Docker - no local installation required)
grpc-list:
	docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 list

grpc-health:
	docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

grpc-describe:
	docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 describe payment.v1.PaymentService

# =============================================================================
# Outbox Processor & Event Streaming
# =============================================================================

run-outbox-processor:
	$(PYTHONPATH) uv run python scripts/run_outbox_processor.py

run-sample-consumer:
	$(PYTHONPATH) uv run python scripts/sample_consumer.py

outbox-logs:
	docker-compose logs -f outbox-processor

# Kafka/Redpanda utilities (via rpk in container)
kafka-topics:
	docker-compose exec redpanda rpk topic list

kafka-create-topics:
	docker-compose exec redpanda rpk topic create payments.paymentauthorized payments.paymentdeclined payments.dlq --partitions 3

kafka-consume:
	docker-compose exec redpanda rpk topic consume payments.paymentauthorized --format json

kafka-consume-dlq:
	docker-compose exec redpanda rpk topic consume payments.dlq --format json

# =============================================================================
# Production Readiness
# =============================================================================

load-test:
	@echo "Running k6 load tests..."
	@echo "Make sure the service is running with 'make up && make migrate'"
	docker run --rm --network=host -v $(CURDIR):/scripts -w /scripts grafana/k6:latest run load-tests/payment_load_test.js

load-test-smoke:
	docker run --rm --network=host -v $(CURDIR):/scripts -w /scripts grafana/k6:latest run --vus 1 --duration 30s load-tests/payment_load_test.js

metrics-check:
	@echo "Checking Prometheus metrics endpoint..."
	curl -s http://localhost:9090/metrics | head -50

metrics-payment:
	@echo "Payment-related metrics:"
	curl -s http://localhost:9090/metrics | grep -E "^(payment_|grpc_|rate_limit)" | head -30
