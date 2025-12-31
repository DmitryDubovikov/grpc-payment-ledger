"""Unit tests for event schema validation using jsonschema."""

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate


# Path to schema files
SCHEMAS_DIR = Path(__file__).parent.parent.parent / "schemas"

# Valid ULID test IDs (Crockford Base32: 0-9, A-H, J-K, M-N, P-T, V-Z - no I, L, O, U or lowercase)
# ULIDs are exactly 26 characters long
VALID_EVENT_ID_1 = "01HW8B00000000000000000001"
VALID_EVENT_ID_2 = "01HW8B00000000000000000002"
VALID_PAYMENT_ID_1 = "01HW8BP0000000000000000001"
VALID_PAYMENT_ID_2 = "01HW8BP0000000000000000002"
VALID_PAYER_ID = "01HW8BR0000000000000000001"
VALID_PAYEE_ID = "01HW8BR0000000000000000002"


@pytest.fixture
def event_envelope_schema() -> dict:
    """Load event envelope JSON schema."""
    schema_path = SCHEMAS_DIR / "event_envelope.json"
    with schema_path.open() as f:
        return json.load(f)


@pytest.fixture
def payment_authorized_schema() -> dict:
    """Load payment authorized JSON schema."""
    schema_path = SCHEMAS_DIR / "payment_authorized.json"
    with schema_path.open() as f:
        return json.load(f)


@pytest.fixture
def dead_letter_schema() -> dict:
    """Load dead letter JSON schema."""
    schema_path = SCHEMAS_DIR / "dead_letter.json"
    with schema_path.open() as f:
        return json.load(f)


class TestEventEnvelopeSchema:
    """Tests for event envelope schema validation."""

    def test_valid_payment_authorized_event(self, event_envelope_schema: dict) -> None:
        """Test valid PaymentAuthorized event passes schema validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_1,
                "amount_cents": 1000,
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        # Should not raise
        validate(instance=event, schema=event_envelope_schema)

    def test_valid_payment_declined_event(self, event_envelope_schema: dict) -> None:
        """Test valid PaymentDeclined event passes schema validation."""
        event = {
            "event_id": VALID_EVENT_ID_2,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_2,
            "event_type": "PaymentDeclined",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_2,
                "error_code": "INSUFFICIENT_FUNDS",
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        validate(instance=event, schema=event_envelope_schema)

    def test_missing_required_field_event_id(self, event_envelope_schema: dict) -> None:
        """Test event without event_id fails validation."""
        event = {
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=event, schema=event_envelope_schema)

        assert "event_id" in str(exc_info.value)

    def test_missing_required_field_aggregate_type(self, event_envelope_schema: dict) -> None:
        """Test event without aggregate_type fails validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=event, schema=event_envelope_schema)

        assert "aggregate_type" in str(exc_info.value)

    def test_missing_required_field_timestamp(self, event_envelope_schema: dict) -> None:
        """Test event without timestamp fails validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=event, schema=event_envelope_schema)

        assert "timestamp" in str(exc_info.value)

    def test_invalid_event_id_format(self, event_envelope_schema: dict) -> None:
        """Test event with invalid ULID format for event_id fails validation."""
        event = {
            "event_id": "invalid-id",  # Not a valid ULID
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError):
            validate(instance=event, schema=event_envelope_schema)

    def test_invalid_aggregate_type(self, event_envelope_schema: dict) -> None:
        """Test event with invalid aggregate_type fails validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "InvalidType",  # Not in enum
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError):
            validate(instance=event, schema=event_envelope_schema)

    def test_additional_properties_not_allowed(self, event_envelope_schema: dict) -> None:
        """Test event with extra properties fails validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
            "extra_field": "not_allowed",  # Additional property
        }

        with pytest.raises(ValidationError):
            validate(instance=event, schema=event_envelope_schema)


class TestPaymentAuthorizedSchema:
    """Tests for PaymentAuthorized event schema validation."""

    def test_valid_payment_authorized_full(self, payment_authorized_schema: dict) -> None:
        """Test valid PaymentAuthorized event with all fields."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_1,
                "payer_account_id": VALID_PAYER_ID,
                "payee_account_id": VALID_PAYEE_ID,
                "amount_cents": 1000,
                "currency": "USD",
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        validate(instance=event, schema=payment_authorized_schema)

    def test_valid_payment_authorized_with_description(self, payment_authorized_schema: dict) -> None:
        """Test valid PaymentAuthorized event with optional description."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_1,
                "payer_account_id": VALID_PAYER_ID,
                "payee_account_id": VALID_PAYEE_ID,
                "amount_cents": 1000,
                "currency": "USD",
                "description": "Test payment",
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        validate(instance=event, schema=payment_authorized_schema)

    def test_missing_payload_payment_id(self, payment_authorized_schema: dict) -> None:
        """Test PaymentAuthorized without payment_id in payload fails."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payer_account_id": VALID_PAYER_ID,
                "payee_account_id": VALID_PAYEE_ID,
                "amount_cents": 1000,
                "currency": "USD",
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=event, schema=payment_authorized_schema)

        assert "payment_id" in str(exc_info.value)

    def test_invalid_amount_cents_zero(self, payment_authorized_schema: dict) -> None:
        """Test PaymentAuthorized with zero amount_cents fails."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_1,
                "payer_account_id": VALID_PAYER_ID,
                "payee_account_id": VALID_PAYEE_ID,
                "amount_cents": 0,  # Minimum is 1
                "currency": "USD",
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError):
            validate(instance=event, schema=payment_authorized_schema)

    def test_invalid_currency_format(self, payment_authorized_schema: dict) -> None:
        """Test PaymentAuthorized with invalid currency format fails."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_1,
                "payer_account_id": VALID_PAYER_ID,
                "payee_account_id": VALID_PAYEE_ID,
                "amount_cents": 1000,
                "currency": "usd",  # Must be uppercase
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError):
            validate(instance=event, schema=payment_authorized_schema)

    def test_invalid_currency_length(self, payment_authorized_schema: dict) -> None:
        """Test PaymentAuthorized with invalid currency length fails."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_1,
                "payer_account_id": VALID_PAYER_ID,
                "payee_account_id": VALID_PAYEE_ID,
                "amount_cents": 1000,
                "currency": "US",  # Must be 3 characters
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError):
            validate(instance=event, schema=payment_authorized_schema)

    def test_wrong_aggregate_type_const(self, payment_authorized_schema: dict) -> None:
        """Test PaymentAuthorized with wrong aggregate_type fails."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Account",  # Must be "Payment"
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_1,
                "payer_account_id": VALID_PAYER_ID,
                "payee_account_id": VALID_PAYEE_ID,
                "amount_cents": 1000,
                "currency": "USD",
            },
            "timestamp": "2024-06-15T10:30:00Z",
        }

        with pytest.raises(ValidationError):
            validate(instance=event, schema=payment_authorized_schema)


class TestDeadLetterSchema:
    """Tests for dead letter event schema validation."""

    def test_valid_dead_letter_event(self, dead_letter_schema: dict) -> None:
        """Test valid dead letter event passes validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {
                "payment_id": VALID_PAYMENT_ID_1,
                "amount_cents": 1000,
            },
            "timestamp": "2024-06-15T10:30:00Z",
            "retry_count": 5,
            "failed_at": "2024-06-15T10:35:00Z",
            "error": "max_retries_exceeded",
        }

        validate(instance=event, schema=dead_letter_schema)

    def test_missing_retry_count(self, dead_letter_schema: dict) -> None:
        """Test dead letter event without retry_count fails validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
            "failed_at": "2024-06-15T10:35:00Z",
            "error": "max_retries_exceeded",
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=event, schema=dead_letter_schema)

        assert "retry_count" in str(exc_info.value)

    def test_missing_failed_at(self, dead_letter_schema: dict) -> None:
        """Test dead letter event without failed_at fails validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
            "retry_count": 5,
            "error": "max_retries_exceeded",
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=event, schema=dead_letter_schema)

        assert "failed_at" in str(exc_info.value)

    def test_missing_error(self, dead_letter_schema: dict) -> None:
        """Test dead letter event without error fails validation."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
            "retry_count": 5,
            "failed_at": "2024-06-15T10:35:00Z",
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=event, schema=dead_letter_schema)

        assert "error" in str(exc_info.value)

    def test_retry_count_minimum_zero(self, dead_letter_schema: dict) -> None:
        """Test dead letter event with retry_count of 0 is valid."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
            "retry_count": 0,
            "failed_at": "2024-06-15T10:35:00Z",
            "error": "immediate_failure",
        }

        validate(instance=event, schema=dead_letter_schema)

    def test_retry_count_negative_fails(self, dead_letter_schema: dict) -> None:
        """Test dead letter event with negative retry_count fails."""
        event = {
            "event_id": VALID_EVENT_ID_1,
            "aggregate_type": "Payment",
            "aggregate_id": VALID_PAYMENT_ID_1,
            "event_type": "PaymentAuthorized",
            "payload": {},
            "timestamp": "2024-06-15T10:30:00Z",
            "retry_count": -1,  # Must be >= 0
            "failed_at": "2024-06-15T10:35:00Z",
            "error": "some_error",
        }

        with pytest.raises(ValidationError):
            validate(instance=event, schema=dead_letter_schema)
