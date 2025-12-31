from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    database_url: str = "postgresql+asyncpg://payment:payment@localhost:5432/payment_db"
    redis_url: str = "redis://localhost:6379/0"
    redpanda_brokers: str = "localhost:19092"

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    grpc_port: int = 50051

    # Outbox processor settings
    outbox_batch_size: int = 100
    outbox_poll_interval_seconds: float = 1.0
    outbox_max_retries: int = 5
    outbox_base_delay_seconds: float = 1.0
    outbox_max_delay_seconds: float = 60.0

    # Kafka/Redpanda topic settings
    kafka_topic_prefix: str = "payments"


settings = Settings()
