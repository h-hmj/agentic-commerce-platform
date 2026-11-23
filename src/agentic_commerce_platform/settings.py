"""Environment-driven application configuration."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentic_commerce_platform.domain.errors import ConfigurationError

__all__ = [
    "AppEnvironment",
    "LogFormat",
    "LogLevel",
    "Settings",
    "get_settings",
]


class AppEnvironment(StrEnum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Standard library logging levels exposed through configuration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(StrEnum):
    """Supported observability output formats."""

    CONSOLE = "console"
    JSON = "json"


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables and `.env`.

    Configuration is validated at process startup. Secrets use :class:`SecretStr`
    so accidental string formatting or logging of a settings object does not
    reveal the API key.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
        str_strip_whitespace=True,
    )

    app_name: str = Field(
        default="agentic-commerce-platform",
        min_length=1,
        max_length=100,
        description="Human-readable application name.",
    )
    app_version: str = Field(
        default="0.1.0",
        min_length=1,
        max_length=32,
        description="Application version exposed by the health endpoint.",
    )
    app_env: AppEnvironment = Field(
        default=AppEnvironment.DEVELOPMENT,
        description="Runtime environment: development, test, or production.",
    )
    debug: bool = Field(
        default=False,
        description="Enable development-only debug behavior.",
    )
    api_host: str = Field(
        default="127.0.0.1",
        min_length=1,
        max_length=255,
        description="Host used by the Uvicorn command.",
    )
    api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port used by the Uvicorn command.",
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Minimum log level.",
    )
    log_format: LogFormat = Field(
        default=LogFormat.CONSOLE,
        description="Console text or JSON log rendering.",
    )
    llm_provider: str = Field(
        default="mock",
        min_length=1,
        max_length=32,
        description="LLM provider identifier. Phase two supports only mock.",
    )
    llm_api_key: SecretStr = Field(
        default_factory=lambda: SecretStr(""),
        description="Optional LLM API key. Empty by default and never logged.",
    )
    llm_base_url: HttpUrl | None = Field(
        default=None,
        description="Optional provider base URL. Empty in phase two.",
    )
    llm_model: str = Field(
        default="mock-llm-v1",
        min_length=1,
        max_length=100,
        description="Model identifier passed to a future provider adapter.",
    )

    @field_validator("app_name", "app_version", "api_host", "llm_model", mode="before")
    @classmethod
    def validate_non_blank_text(cls, value: object) -> object:
        """Reject blank string settings before type validation."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("value must not be blank")
            return stripped
        return value

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        """Accept environment names in any case."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        """Accept log levels in any case."""
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("log_format", mode="before")
    @classmethod
    def normalize_log_format(cls, value: object) -> object:
        """Accept log formats in any case."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        """Only allow providers implemented in the current phase."""
        normalized = value.strip().lower()
        if normalized != "mock":
            raise ValueError(
                "the current phase supports only the 'mock' LLM provider; "
                f"got {normalized!r}"
            )
        return normalized

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def normalize_base_url(cls, value: object) -> object:
        """Treat an empty environment variable as an unset URL."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def validate_environment_consistency(self) -> Settings:
        """Prevent debug mode from being enabled in production."""
        if self.app_env is AppEnvironment.PRODUCTION and self.debug:
            raise ValueError("debug must be false when app_env is production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache process-wide settings.

    Raises:
        ConfigurationError: If environment configuration fails validation.
    """
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError(
            "Application configuration is invalid. Check the environment variables."
        ) from exc
