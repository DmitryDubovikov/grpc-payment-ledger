# gRPC Payment Authorization & Ledger Service

Venmo-style payment authorization service demonstrating idempotent payment processing, double-entry ledger accounting, and event-driven architecture.

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

## Features

- **Idempotent Payments**: Same request with same idempotency_key returns cached result
- **Double-Entry Ledger**: Every payment creates balanced DEBIT/CREDIT entries
- **Optimistic Locking**: Prevents concurrent balance overwrites with version tracking
- **Outbox Pattern**: Reliable event publishing with exactly-once semantics
- **gRPC Reflection**: Service discovery and debugging support
- **Health Checks**: Standard gRPC health checking protocol
- **Structured Logging**: JSON-formatted logs with structlog

## Quick Start

Run the service with Docker (no local Python required):

```bash
# Start all services (PostgreSQL, Redis, Redpanda, Payment Service)
make dev-up

# Apply database migrations
make migrate

# Create test accounts
make reset-test-data

# Verify service is running
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

See [Manual Testing Guide](docs/iterations/iteration-1-manual-testing.md) for detailed API testing examples.

### Local Development

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

## gRPC Services

| Service | Method | Description |
|---------|--------|-------------|
| PaymentService | AuthorizePayment | Process payment authorization (idempotent) |
| PaymentService | GetPayment | Retrieve payment details by ID |
| PaymentService | GetAccountBalance | Get account balance |
| Health | Check | Health check endpoint |

## Technology Stack

- **Language**: Python 3.12+
- **RPC**: gRPC (grpcio, grpcio-tools, grpcio-reflection, grpcio-health-checking)
- **Database**: PostgreSQL 16 (SQLAlchemy async, asyncpg)
- **Migrations**: Alembic
- **Cache/Rate Limiting**: Redis 7
- **Event Streaming**: Redpanda (Kafka-compatible)
- **Logging**: structlog
- **Configuration**: pydantic-settings
- **Testing**: pytest, pytest-asyncio, testcontainers
- **Package Manager**: uv

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
│   ├── infrastructure/              # Data access
│   │   ├── database.py              # Database connection
│   │   └── repositories/            # Repository implementations
│   ├── api/                         # gRPC handlers
│   │   └── grpc_handlers.py         # PaymentServiceHandler
│   └── proto/                       # Generated protobuf code
├── alembic/                         # Database migrations
│   └── versions/
│       └── 001_initial_schema.py    # Initial schema
├── tests/                           # Test suite
├── docker-compose.yml               # Infrastructure services
├── Makefile                         # Build commands
└── pyproject.toml                   # Project configuration
```

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://payment:payment@localhost:5432/payment_db` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `REDPANDA_BROKERS` | `localhost:19092` | Redpanda broker addresses |
| `GRPC_PORT` | `50051` | gRPC server port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `json` | Log format (`json` or `console`) |

## Makefile Commands

### Development

| Command | Description |
|---------|-------------|
| `make install` | Install production dependencies |
| `make install-dev` | Install all dependencies (including dev) |
| `make format` | Format code with ruff |
| `make lint` | Run linting checks |
| `make lint-fix` | Fix linting issues automatically |
| `make type-check` | Run mypy type checking |
| `make check` | Run all checks (lint, type-check, test-unit) |

### Testing

| Command | Description |
|---------|-------------|
| `make test` | Run all tests |
| `make test-unit` | Run unit tests only |
| `make test-integration` | Run integration tests |
| `make test-e2e` | Run end-to-end tests |
| `make test-cov` | Run tests with coverage report |

### Infrastructure

| Command | Description |
|---------|-------------|
| `make up` | Start PostgreSQL, Redis, Redpanda |
| `make docker-down` | Stop all containers |
| `make migrate` | Apply database migrations |
| `make proto` | Generate protobuf code |
| `make run` | Start gRPC server locally |
| `make clean` | Remove generated files and caches |

### Database

| Command | Description |
|---------|-------------|
| `make db-migrate MSG="description"` | Create new migration |
| `make db-upgrade` | Apply all migrations |
| `make db-downgrade` | Rollback last migration |
| `make db-history` | Show migration history |
| `make db-current` | Show current revision |

## Documentation

- [gRPC API](docs/proto/payment-service.md)
- [Database Schema](docs/database/schema.md)
- [Event Schemas](docs/events/event-schemas.md)

## Development

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (optional, for local development)
- uv (optional, for local development)

> **Note**: `grpcurl` runs via Docker — no local installation required.

### Running Tests

```bash
# All tests
make test

# With coverage
make test-cov

# Only unit tests
make test-unit

# Integration tests (requires infrastructure)
make test-integration
```

### gRPC Debugging

All `grpcurl` commands run via Docker (no local installation required):

```bash
# List services
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 list

# Describe service
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 describe payment.v1.PaymentService

# Health check
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# Authorize payment
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "payer_account_id": "01HY1234567890ABCDEFGHIJ",
  "payee_account_id": "01HY0987654321JIHGFEDCBA",
  "amount_cents": 5000,
  "currency": "USD",
  "description": "Payment for services"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment

# Get account balance
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{"account_id": "01HY1234567890ABCDEFGHIJ"}' \
  localhost:50051 payment.v1.PaymentService/GetAccountBalance
```

**Tip**: Add an alias to simplify commands:
```bash
alias grpcurl='docker run --rm --network=host fullstorydev/grpcurl'
```

## Event Streaming

The service implements the **Outbox Pattern** for reliable event publishing to Kafka/Redpanda.

### Architecture

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
          │                      │  │ Kafka/Redpanda│  │
          │                      │  └───────┬───────┘  │
          ▼                      └──────────┼──────────┘
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

### How the Outbox Pattern Works

1. **Atomic Write**: When a payment is processed, the service writes the payment record AND an outbox event in the same database transaction
2. **Background Processing**: The OutboxProcessor polls the outbox table for unpublished events
3. **Reliable Delivery**: Events are published to Kafka with exactly-once semantics (idempotent producer)
4. **Retry with Backoff**: Failed events are retried with exponential backoff
5. **Dead Letter Queue**: Events exceeding max retries are sent to a DLQ for manual inspection

### Event Topics

| Topic | Description |
|-------|-------------|
| `payments.paymentauthorized` | Successful payment authorizations |
| `payments.paymentdeclined` | Declined payment attempts |
| `payments.dlq` | Dead letter queue for failed events |

### Running the Outbox Processor

```bash
# Run as Docker service (recommended for production)
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

See [Event Schemas](docs/events/event-schemas.md) for detailed event documentation.

### Kafka/Redpanda Commands

| Command | Description |
|---------|-------------|
| `make kafka-topics` | List all topics |
| `make kafka-create-topics` | Create required topics |
| `make kafka-consume` | Consume payment authorized events |
| `make kafka-consume-dlq` | Consume dead letter queue |

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDPANDA_BROKERS` | `localhost:19092` | Kafka/Redpanda broker addresses |
| `KAFKA_TOPIC_PREFIX` | `payments` | Topic name prefix |
| `OUTBOX_BATCH_SIZE` | `100` | Events per batch |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `1.0` | Polling interval |
| `OUTBOX_MAX_RETRIES` | `5` | Max retry attempts before DLQ |
| `OUTBOX_BASE_DELAY_SECONDS` | `1.0` | Base delay for exponential backoff |
| `OUTBOX_MAX_DELAY_SECONDS` | `60.0` | Maximum backoff delay |

---

## Domain Model

### Core Value Objects

- **Money**: Immutable value object representing monetary amounts (amount_cents + currency)

### Entities

- **Account**: User account with owner, currency, and status
- **AccountBalance**: Denormalized balance with optimistic locking (version field)
- **Payment**: Payment record with idempotency key and status
- **LedgerEntry**: Double-entry accounting entries (DEBIT/CREDIT)
- **IdempotencyRecord**: Tracks idempotency keys with 24h expiry
- **OutboxEvent**: Transactional outbox for reliable event publishing

### Payment Flow

1. Client sends `AuthorizePayment` with idempotency key
2. Service checks for existing idempotency record
3. If found and completed, returns cached response (DUPLICATE status)
4. Validates accounts exist and payer has sufficient funds
5. Locks balances for update (optimistic locking)
6. Creates payment record
7. Creates DEBIT entry for payer, CREDIT entry for payee
8. Updates account balances with new version
9. Writes outbox event for downstream systems
10. Marks idempotency key as completed
11. Commits transaction atomically

## License

MIT
