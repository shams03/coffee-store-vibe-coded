"""
Application configuration from environment.
Secrets and URLs are read from env; no defaults for secrets.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment (and .env file)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop"

    # JWT
    jwt_secret_key: str = "change-me-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # External services
    payment_service_url: str = "https://challenge.trio.dev/api/v1/payment"
    notification_service_url: str = "https://challenge.trio.dev/api/v1/notification"

    # Observability
    sentry_dsn: Optional[str] = None
    app_env: str = "development"
    log_level: str = "INFO"

    # API
    api_prefix: str = "/api/v1"

    # Timeouts (seconds)
    payment_request_timeout: float = 10.0
    notification_request_timeout: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
