# gRPC Payment Authorization & Ledger Service

**A production-grade pet project demonstrating backend engineering skills in building financial systems.**

---

## About This Project

This is a **portfolio project** showcasing expertise in:

- **Distributed Systems Design** — Idempotent APIs, optimistic locking, exactly-once event delivery
- **Financial Domain Modeling** — Double-entry ledger accounting, atomic balance updates
- **Event-Driven Architecture** — Transactional Outbox pattern with Kafka/Redpanda
- **gRPC API Development** — Protocol Buffers, reflection, health checks, interceptors
- **Production-Ready Practices** — Rate limiting, structured logging, Prometheus metrics, comprehensive testing

### Tech Stack

| Category | Technology | Purpose |
|----------|------------|---------|
| **API** | gRPC + Protocol Buffers | High-performance RPC with strong typing |
| **Language** | Python 3.12, async/await | Modern async programming |
| **Database** | PostgreSQL 16 | ACID transactions, JSONB, partial indexes |
| **ORM** | SQLAlchemy 2.0 (async) | Async database access with type safety |
| **Migrations** | Alembic | Version-controlled schema changes |
| **Cache** | Redis 7 | Rate limiting with sliding window algorithm |
| **Events** | Redpanda (Kafka-compatible) | Event streaming with exactly-once semantics |
| **Observability** | structlog + Prometheus | JSON logging, metrics collection |
| **Testing** | pytest + testcontainers | Unit, integration, E2E tests with real DBs |
| **Package Manager** | uv | Fast Python dependency management |
| **Containers** | Docker + Docker Compose | Local development, multi-stage builds |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         gRPC Clients                                │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼ :50051
┌─────────────────────────────────────────────────────────────────────┐
│                      Payment Service (gRPC)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Authorize    │  │ GetPayment   │  │ GetAccountBalance        │  │
│  │ Payment      │  │              │  │                          │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    PaymentService                             │  │
│  │  - Idempotency check (24h expiry)                            │  │
│  │  - Account validation                                         │  │
│  │  - Balance verification                                       │  │
│  │  - Double-entry ledger (DEBIT/CREDIT)                        │  │
│  │  - Outbox pattern (reliable events)                          │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌──────────┐         ┌──────────┐         ┌──────────┐
   │PostgreSQL│         │  Redis   │         │ Redpanda │
   │  :5432   │         │  :6379   │         │  :19092  │
   │          │         │          │         │          │
   │ accounts │         │rate limit│         │ events   │
   │ payments │         │  cache   │         │          │
   │ ledger   │         │          │         │          │
   │ outbox   │         │          │         │          │
   └──────────┘         └──────────┘         └──────────┘
```

---

## Key Features

### Idempotent Payment Processing
- Same `idempotency_key` always returns the same result
- 24-hour key expiry with database-backed storage
- Prevents duplicate charges on network retries

### Double-Entry Ledger
- Every payment creates balanced DEBIT/CREDIT entries
- Audit trail with `balance_after_cents` for each entry
- Sum of all entries always equals zero (accounting invariant)

### Optimistic Locking
- Version-based concurrency control on account balances
- Prevents race conditions in concurrent payments
- No overdrafts even under high concurrency

### Transactional Outbox Pattern
- Events written to DB in same transaction as business data
- Background processor publishes to Kafka with exactly-once semantics
- Exponential backoff retry with Dead Letter Queue
- Guarantees no lost events, no duplicate events

### Production Observability
- Structured JSON logging with correlation IDs
- Prometheus metrics (payment latency, error rates, outbox lag)
- gRPC health checks for load balancer integration
- gRPC reflection for runtime service discovery

### Rate Limiting
- Redis-based sliding window rate limiter
- Configurable per-endpoint limits
- Returns `RESOURCE_EXHAUSTED` gRPC status when exceeded

---

## Quick Start

Run the complete stack with Docker (no local Python required):

```bash
# Start all services (PostgreSQL, Redis, Redpanda, Payment Service)
make dev-up

# Apply database migrations
make migrate

# Create test accounts with initial balances
make reset-test-data

# Verify service is running
docker run --rm --network=host fullstorydev/grpcurl \
  -plaintext localhost:50051 grpc.health.v1.Health/Check
```

### Make a Test Payment

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 5000,
  "currency": "USD",
  "description": "Coffee payment"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

See [Manual Testing Guide](docs/iterations/iteration-1-manual-testing.md) for more examples.

---

## Local Development

For editing code and running locally:

```bash
# Install dependencies (requires Python 3.12+ and uv)
make install-dev

# Start infrastructure only
make up

# Apply migrations
make migrate

# Generate protobuf code
make proto

# Run gRPC server locally
make run
```

### Running Tests

```bash
# All tests
make test

# With coverage
make test-cov

# Unit tests only (fast, no containers)
make test-unit

# Integration tests (requires infrastructure)
make test-integration

# E2E tests (requires full stack running)
make test-e2e
```

### Code Quality

```bash
# Format code
make format

# Lint
make lint

# Type check
make type-check

# All checks
make check
```

---

## gRPC API

| Service | Method | Description |
|---------|--------|-------------|
| PaymentService | AuthorizePayment | Process payment authorization (idempotent) |
| PaymentService | GetPayment | Retrieve payment details by ID |
| PaymentService | GetAccountBalance | Get account balance |
| Health | Check | Health check endpoint |

### Example: Authorize Payment

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "unique-key-123",
  "payer_account_id": "acc-payer-001",
  "payee_account_id": "acc-payee-002",
  "amount_cents": 1000,
  "currency": "USD"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

Response:
```json
{
  "paymentId": "01JGHX...",
  "status": "PAYMENT_STATUS_AUTHORIZED",
  "processedAt": "2024-01-15T10:30:00Z"
}
```

### gRPC Debugging

```bash
# List services
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 list

# Describe service
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 describe payment.v1.PaymentService

# Health check
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

**Tip**: Add an alias to simplify commands:
```bash
alias grpcurl='docker run --rm --network=host fullstorydev/grpcurl'
```

---

## Event Streaming (Outbox Pattern)

```
┌─────────────────────┐          ┌─────────────────────┐
│   Payment Service   │          │   Outbox Processor  │
│                     │          │   (Background)      │
│  ┌───────────────┐  │          │                     │
│  │ PaymentService│  │          │  ┌───────────────┐  │
│  │               │  │          │  │ Poll outbox   │  │
│  │ 1. Process    │  │          │  │ table for     │  │
│  │    payment    │  │          │  │ unpublished   │  │
│  │               │  │          │  │ events        │  │
│  │ 2. Write to   │  │          │  └───────┬───────┘  │
│  │    outbox     │──┼──────────┼──────────┘          │
│  │    table      │  │          │                     │
│  └───────────────┘  │          │  ┌───────────────┐  │
└─────────────────────┘          │  │ Publish to    │  │
         │                       │  │ Kafka/Redpanda│  │
         │                       │  └───────┬───────┘  │
         ▼                       └──────────┼──────────┘
┌─────────────────────┐                     │
│     PostgreSQL      │                     ▼
│  ┌───────────────┐  │          ┌─────────────────────┐
│  │ outbox table  │  │          │   Redpanda/Kafka    │
│  │               │  │          │                     │
│  │ - event_type  │  │          │ Topics:             │
│  │ - payload     │  │          │ - payments.payment  │
│  │ - published_at│  │          │   authorized        │
│  │ - retry_count │  │          │ - payments.payment  │
│  └───────────────┘  │          │   declined          │
└─────────────────────┘          │ - payments.dlq      │
                                 └─────────────────────┘
```

### Event Topics

| Topic | Description |
|-------|-------------|
| `payments.paymentauthorized` | Successful payment authorizations |
| `payments.paymentdeclined` | Declined payment attempts |
| `payments.dlq` | Dead letter queue for failed events |

### Running the Outbox Processor

```bash
# Run as Docker service
docker-compose up -d outbox-processor

# View logs
make outbox-logs

# Run locally for development
make run-outbox-processor
```

### Consuming Events

```bash
# Run the sample consumer
make run-sample-consumer

# Or consume directly with rpk
make kafka-consume
```

---

## Project Structure

```
grpc-payment-ledger/
├── proto/
│   └── payment/v1/payment.proto     # gRPC contract
├── src/payment_service/
│   ├── main.py                      # Server entrypoint
│   ├── config.py                    # Settings (pydantic-settings)
│   ├── grpc_server.py               # gRPC server setup
│   ├── logging.py                   # Structured logging config
│   ├── domain/                      # Domain models
│   │   └── models.py                # Money, Account, Payment, LedgerEntry
│   ├── application/                 # Business logic
│   │   ├── services.py              # PaymentService
│   │   └── unit_of_work.py          # Unit of Work pattern
│   ├── infrastructure/              # Data access & external services
│   │   ├── database.py              # Database connection
│   │   ├── repositories/            # Repository implementations
│   │   ├── event_publisher.py       # Outbox processor
│   │   ├── rate_limiter.py          # Sliding window rate limiter
│   │   ├── redis_client.py          # Redis connection
│   │   └── metrics.py               # Prometheus metrics
│   ├── api/                         # gRPC handlers
│   │   ├── grpc_handlers.py         # PaymentServiceHandler
│   │   └── interceptors.py          # Rate limiting, metrics
│   └── proto/                       # Generated protobuf code
├── alembic/                         # Database migrations
├── tests/
│   ├── unit/                        # Domain logic tests
│   ├── integration/                 # Repository & gRPC tests
│   └── e2e/                         # Full stack tests
├── schemas/                         # JSON schemas for events
├── scripts/                         # Utility scripts
├── load-tests/                      # k6 load testing
├── chaos-tests/                     # Chaos engineering scenarios
├── docs/                            # Documentation
├── docker-compose.yml               # Infrastructure services
├── Dockerfile                       # Multi-stage build
├── Makefile                         # Build commands
└── pyproject.toml                   # Project configuration
```

---

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `REDPANDA_BROKERS` | `localhost:19092` | Kafka/Redpanda broker addresses |
| `GRPC_PORT` | `50051` | gRPC server port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `json` | Log format (`json` or `console`) |
| `OUTBOX_BATCH_SIZE` | `100` | Events per batch |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `1.0` | Polling interval |
| `OUTBOX_MAX_RETRIES` | `5` | Max retry attempts before DLQ |

---

## Documentation

- [gRPC API Reference](docs/proto/payment-service.md)
- [Database Schema](docs/database/schema.md)
- [Event Schemas](docs/events/event-schemas.md)
- [Manual Testing Guide](docs/iterations/iteration-1-manual-testing.md)

---

## Makefile Commands

### Development

| Command | Description |
|---------|-------------|
| `make install-dev` | Install all dependencies |
| `make format` | Format code with ruff |
| `make lint` | Run linting checks |
| `make type-check` | Run mypy type checking |
| `make check` | Run all checks |

### Testing

| Command | Description |
|---------|-------------|
| `make test` | Run all tests |
| `make test-unit` | Run unit tests only |
| `make test-integration` | Run integration tests |
| `make test-e2e` | Run end-to-end tests |
| `make test-cov` | Run tests with coverage |

### Infrastructure

| Command | Description |
|---------|-------------|
| `make up` | Start PostgreSQL, Redis, Redpanda |
| `make dev-up` | Start all services including app |
| `make docker-down` | Stop all containers |
| `make migrate` | Apply database migrations |
| `make proto` | Generate protobuf code |
| `make run` | Start gRPC server locally |

### Kafka

| Command | Description |
|---------|-------------|
| `make kafka-topics` | List all topics |
| `make kafka-create-topics` | Create required topics |
| `make kafka-consume` | Consume payment events |
| `make kafka-consume-dlq` | Consume dead letter queue |

---

## License

MIT
