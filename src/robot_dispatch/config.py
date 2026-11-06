from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables with the DISPATCH_ prefix."""

    model_config = SettingsConfigDict(env_prefix="DISPATCH_", env_file=".env", extra="ignore")

    app_name: str = "robot-dispatch"
    environment: str = "local"
    log_level: str = "INFO"
    log_json: bool = True

    api_key: str | None = None

    database_url: str = "postgresql+asyncpg://dispatch:dispatch@localhost:5432/dispatch"
    rabbitmq_url: str = "amqp://dispatch:dispatch@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"

    rabbitmq_connect_retries: int = 10
    rabbitmq_connect_delay_seconds: float = 2.0

    dispatcher_poll_interval_ms: int = 250
    dispatcher_batch_size: int = 10
    outbox_poll_interval_ms: int = 200
    outbox_batch_size: int = 50
    outbox_max_attempts: int = 10
    reaper_interval_ms: int = 1000

    robot_offline_after_seconds: int = 30
    default_task_timeout_seconds: int = 120
    default_max_attempts: int = 3

    retry_base_delay_seconds: float = 5.0
    retry_max_delay_seconds: float = 120.0
    retry_jitter_ratio: float = 0.2

    result_retry_max: int = 3
    result_retry_delay_ms: int = 5000
    consumer_prefetch: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
