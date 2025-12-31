"""Unit tests for outbox-related configuration settings."""

import os
from unittest.mock import patch

from payment_service.config import Settings


class TestOutboxSettings:
    """Tests for outbox configuration settings."""

    def test_default_outbox_settings(self) -> None:
        """Test default outbox configuration values."""
        settings = Settings()

        assert settings.outbox_batch_size == 100
        assert settings.outbox_poll_interval_seconds == 1.0
        assert settings.outbox_max_retries == 5
        assert settings.outbox_base_delay_seconds == 1.0
        assert settings.outbox_max_delay_seconds == 60.0
        assert settings.kafka_topic_prefix == "payments"

    def test_custom_outbox_settings_from_env(self) -> None:
        """Test outbox settings can be configured via environment variables."""
        env_vars = {
            "OUTBOX_BATCH_SIZE": "50",
            "OUTBOX_POLL_INTERVAL_SECONDS": "2.5",
            "OUTBOX_MAX_RETRIES": "10",
            "OUTBOX_BASE_DELAY_SECONDS": "0.5",
            "OUTBOX_MAX_DELAY_SECONDS": "120.0",
            "KAFKA_TOPIC_PREFIX": "custom-payments",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings()

            assert settings.outbox_batch_size == 50
            assert settings.outbox_poll_interval_seconds == 2.5
            assert settings.outbox_max_retries == 10
            assert settings.outbox_base_delay_seconds == 0.5
            assert settings.outbox_max_delay_seconds == 120.0
            assert settings.kafka_topic_prefix == "custom-payments"

    def test_redpanda_brokers_default(self) -> None:
        """Test default Redpanda broker configuration."""
        settings = Settings()

        assert settings.redpanda_brokers == "localhost:19092"

    def test_redpanda_brokers_from_env(self) -> None:
        """Test Redpanda brokers can be configured via environment."""
        with patch.dict(os.environ, {"REDPANDA_BROKERS": "broker1:9092,broker2:9092"}, clear=False):
            settings = Settings()

            assert settings.redpanda_brokers == "broker1:9092,broker2:9092"

    def test_outbox_batch_size_positive(self) -> None:
        """Verify batch size is a positive integer by default."""
        settings = Settings()

        assert settings.outbox_batch_size > 0
        assert isinstance(settings.outbox_batch_size, int)

    def test_outbox_poll_interval_positive(self) -> None:
        """Verify poll interval is a positive float by default."""
        settings = Settings()

        assert settings.outbox_poll_interval_seconds > 0
        assert isinstance(settings.outbox_poll_interval_seconds, float)

    def test_outbox_max_retries_non_negative(self) -> None:
        """Verify max retries is non-negative by default."""
        settings = Settings()

        assert settings.outbox_max_retries >= 0
        assert isinstance(settings.outbox_max_retries, int)

    def test_outbox_delay_settings_ordering(self) -> None:
        """Verify base delay is less than or equal to max delay."""
        settings = Settings()

        assert settings.outbox_base_delay_seconds <= settings.outbox_max_delay_seconds
