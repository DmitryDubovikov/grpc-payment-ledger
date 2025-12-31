# gRPC API - Payment Service

## Overview

The Payment Service provides gRPC APIs for payment authorization and account management.

**Package**: `payment.v1`
**Service**: `PaymentService`
**Port**: `50051`

---

## Service Definition

```protobuf
service PaymentService {
  rpc AuthorizePayment(AuthorizePaymentRequest) returns (AuthorizePaymentResponse);
  rpc GetPayment(GetPaymentRequest) returns (GetPaymentResponse);
  rpc GetAccountBalance(GetAccountBalanceRequest) returns (GetAccountBalanceResponse);
}
```

---

## AuthorizePayment

Process a payment authorization request. Idempotent - same idempotency_key returns cached response.

### Request

```protobuf
message AuthorizePaymentRequest {
  string idempotency_key = 1;    // Required. Unique key (UUID v4 recommended)
  string payer_account_id = 2;   // Required. Payer account ID (ULID)
  string payee_account_id = 3;   // Required. Payee account ID (ULID)
  int64 amount_cents = 4;        // Required. Amount in cents (must be positive)
  string currency = 5;           // Required. ISO 4217 code (e.g., "USD")
  string description = 6;        // Optional. Payment memo
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| idempotency_key | string | Yes | Unique identifier for this payment attempt. Use UUID v4. Same key = same response. |
| payer_account_id | string | Yes | Account ID of the sender (ULID format) |
| payee_account_id | string | Yes | Account ID of the recipient (ULID format) |
| amount_cents | int64 | Yes | Payment amount in smallest currency unit (e.g., cents for USD) |
| currency | string | Yes | ISO 4217 currency code (3 characters) |
| description | string | No | Optional memo or note for the payment |

### Response

```protobuf
message AuthorizePaymentResponse {
  string payment_id = 1;         // ULID of created payment
  PaymentStatus status = 2;      // Authorization result
  PaymentError error = 3;        // Error details if DECLINED
  string processed_at = 4;       // RFC 3339 timestamp
}
```

| Field | Type | Description |
|-------|------|-------------|
| payment_id | string | Unique payment identifier (ULID). Empty if declined. |
| status | PaymentStatus | Result of the authorization |
| error | PaymentError | Error details (only populated if status is DECLINED) |
| processed_at | string | ISO 8601 timestamp when the payment was processed |

### Payment Status

```protobuf
enum PaymentStatus {
  PAYMENT_STATUS_UNSPECIFIED = 0;
  PAYMENT_STATUS_AUTHORIZED = 1;
  PAYMENT_STATUS_DECLINED = 2;
  PAYMENT_STATUS_DUPLICATE = 3;
}
```

| Status | Value | Meaning |
|--------|-------|---------|
| PAYMENT_STATUS_UNSPECIFIED | 0 | Default value, should not occur |
| PAYMENT_STATUS_AUTHORIZED | 1 | Payment authorized successfully |
| PAYMENT_STATUS_DECLINED | 2 | Payment declined (see error field) |
| PAYMENT_STATUS_DUPLICATE | 3 | Idempotent replay of existing payment |

### Payment Error

```protobuf
message PaymentError {
  PaymentErrorCode code = 1;
  string message = 2;
}

enum PaymentErrorCode {
  PAYMENT_ERROR_CODE_UNSPECIFIED = 0;
  PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS = 1;
  PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND = 2;
  PAYMENT_ERROR_CODE_INVALID_AMOUNT = 3;
  PAYMENT_ERROR_CODE_SAME_ACCOUNT = 4;
  PAYMENT_ERROR_CODE_CURRENCY_MISMATCH = 5;
  PAYMENT_ERROR_CODE_RATE_LIMITED = 6;
}
```

| Error Code | Value | Meaning |
|------------|-------|---------|
| PAYMENT_ERROR_CODE_UNSPECIFIED | 0 | Unknown error |
| PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS | 1 | Payer has insufficient balance |
| PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND | 2 | Payer or payee account not found |
| PAYMENT_ERROR_CODE_INVALID_AMOUNT | 3 | Amount is zero or negative |
| PAYMENT_ERROR_CODE_SAME_ACCOUNT | 4 | Cannot transfer to same account |
| PAYMENT_ERROR_CODE_CURRENCY_MISMATCH | 5 | Account currency doesn't match request |
| PAYMENT_ERROR_CODE_RATE_LIMITED | 6 | Too many requests |

### gRPC Status Codes

| gRPC Status | Condition |
|-------------|-----------|
| OK | Request processed (check response status for result) |
| INVALID_ARGUMENT | Missing required fields |
| INTERNAL | Unexpected server error |

### Example

**Request:**

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "payer_account_id": "01HY1234567890ABCDEFGHIJ",
  "payee_account_id": "01HY0987654321JIHGFEDCBA",
  "amount_cents": 5000,
  "currency": "USD",
  "description": "Payment for coffee"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment
```

**Success Response:**

```json
{
  "paymentId": "01HYABCDEF1234567890QRST",
  "status": "PAYMENT_STATUS_AUTHORIZED",
  "processedAt": "2024-01-15T10:30:00.123456+00:00"
}
```

**Declined Response:**

```json
{
  "paymentId": "",
  "status": "PAYMENT_STATUS_DECLINED",
  "error": {
    "code": "PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS",
    "message": "Insufficient funds"
  },
  "processedAt": "2024-01-15T10:30:00.123456+00:00"
}
```

**Duplicate Response (Idempotent Replay):**

```json
{
  "paymentId": "01HYABCDEF1234567890QRST",
  "status": "PAYMENT_STATUS_DUPLICATE",
  "processedAt": "2024-01-15T10:25:00.000000+00:00"
}
```

---

## GetPayment

Retrieve payment details by ID.

### Request

```protobuf
message GetPaymentRequest {
  string payment_id = 1;  // Required. Payment ID (ULID)
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| payment_id | string | Yes | Payment identifier (ULID format) |

### Response

```protobuf
message GetPaymentResponse {
  Payment payment = 1;
}

message Payment {
  string payment_id = 1;
  string payer_account_id = 2;
  string payee_account_id = 3;
  int64 amount_cents = 4;
  string currency = 5;
  PaymentStatus status = 6;
  string description = 7;
  string created_at = 8;
  string updated_at = 9;
}
```

| Field | Type | Description |
|-------|------|-------------|
| payment_id | string | Unique payment identifier (ULID) |
| payer_account_id | string | Account ID of the sender |
| payee_account_id | string | Account ID of the recipient |
| amount_cents | int64 | Payment amount in cents |
| currency | string | ISO 4217 currency code |
| status | PaymentStatus | Payment status |
| description | string | Payment memo (may be empty) |
| created_at | string | ISO 8601 timestamp when created |
| updated_at | string | ISO 8601 timestamp when last updated |

### gRPC Status Codes

| gRPC Status | Condition |
|-------------|-----------|
| OK | Payment found |
| INVALID_ARGUMENT | payment_id is empty |
| NOT_FOUND | Payment does not exist |

### Example

**Request:**

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{"payment_id": "01HYABCDEF1234567890QRST"}' \
  localhost:50051 payment.v1.PaymentService/GetPayment
```

**Response:**

```json
{
  "payment": {
    "paymentId": "01HYABCDEF1234567890QRST",
    "payerAccountId": "01HY1234567890ABCDEFGHIJ",
    "payeeAccountId": "01HY0987654321JIHGFEDCBA",
    "amountCents": "5000",
    "currency": "USD",
    "status": "PAYMENT_STATUS_AUTHORIZED",
    "description": "Payment for coffee",
    "createdAt": "2024-01-15T10:30:00.123456+00:00",
    "updatedAt": "2024-01-15T10:30:00.123456+00:00"
  }
}
```

---

## GetAccountBalance

Retrieve account balance.

### Request

```protobuf
message GetAccountBalanceRequest {
  string account_id = 1;  // Required. Account ID (ULID)
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| account_id | string | Yes | Account identifier (ULID format) |

### Response

```protobuf
message GetAccountBalanceResponse {
  string account_id = 1;
  int64 available_balance_cents = 2;
  int64 pending_balance_cents = 3;
  string currency = 4;
}
```

| Field | Type | Description |
|-------|------|-------------|
| account_id | string | Account identifier |
| available_balance_cents | int64 | Available balance in cents |
| pending_balance_cents | int64 | Pending balance in cents (reserved but not settled) |
| currency | string | ISO 4217 currency code |

### gRPC Status Codes

| gRPC Status | Condition |
|-------------|-----------|
| OK | Account balance found |
| INVALID_ARGUMENT | account_id is empty |
| NOT_FOUND | Account balance record does not exist |

### Example

**Request:**

```bash
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{"account_id": "01HY1234567890ABCDEFGHIJ"}' \
  localhost:50051 payment.v1.PaymentService/GetAccountBalance
```

**Response:**

```json
{
  "accountId": "01HY1234567890ABCDEFGHIJ",
  "availableBalanceCents": "95000",
  "pendingBalanceCents": "0",
  "currency": "USD"
}
```

---

## Health Check

Standard gRPC health checking protocol.

### Example

```bash
# Overall service health
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# Specific service health
docker run --rm --network=host fullstorydev/grpcurl -plaintext -d '{"service": "payment.v1.PaymentService"}' \
  localhost:50051 grpc.health.v1.Health/Check
```

**Response:**

```json
{
  "status": "SERVING"
}
```

---

## Service Discovery

gRPC reflection is enabled for service discovery and debugging.

```bash
# List all services
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 list

# Output:
# grpc.health.v1.Health
# grpc.reflection.v1alpha.ServerReflection
# payment.v1.PaymentService

# Describe a service
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 describe payment.v1.PaymentService

# Describe a message
docker run --rm --network=host fullstorydev/grpcurl -plaintext localhost:50051 describe payment.v1.AuthorizePaymentRequest
```

---

## Idempotency

The `AuthorizePayment` method is idempotent using the `idempotency_key` field.

### Behavior

1. First request with a new idempotency_key: Payment is processed normally
2. Subsequent requests with the same idempotency_key:
   - If original payment succeeded: Returns `PAYMENT_STATUS_DUPLICATE` with original payment_id
   - If original payment failed: Returns the same decline response

### Key Expiry

Idempotency keys expire after 24 hours. After expiry, the same key can be reused for a new payment.

### Best Practices

- Use UUID v4 for idempotency keys
- Generate a new key for each logical payment attempt
- Store the idempotency key client-side to handle retries
- Retry with the same key on network failures

---

## Error Handling

### Validation Errors

All required fields are validated before processing. Missing fields result in `INVALID_ARGUMENT` status.

### Business Errors

Business rule violations (insufficient funds, account not found, etc.) return `OK` status with `PAYMENT_STATUS_DECLINED` and an error message.

### Transient Errors

For transient errors (database unavailable, etc.), retry with the same idempotency_key.
