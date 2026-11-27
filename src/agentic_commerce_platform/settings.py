"""Environment-driven application configuration."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

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

    # Phase-four persistence, memory, and retrieval configuration.
    database_url: str = Field(
        default="sqlite:///./data/agentic_commerce.db",
        min_length=1,
        max_length=500,
        description="SQLAlchemy database URL. SQLite is the local default.",
    )
    database_echo: bool = Field(
        default=False,
        description="Echo SQL statements for local debugging.",
    )
    redis_url: SecretStr = Field(
        default_factory=lambda: SecretStr("redis://localhost:6379/0"),
        description="Redis URL, protected because it may contain credentials.",
    )
    redis_enabled: bool = Field(
        default=False,
        description="Enable Redis memory; false uses InMemoryMemoryStore.",
    )
    redis_key_prefix: str = Field(
        default="agentic-commerce",
        min_length=1,
        max_length=80,
        description="Prefix applied to every Redis key.",
    )
    vector_store_type: Literal["local"] = Field(
        default="local",
        description="Local vector store implementation.",
    )
    vector_collection_name: str = Field(
        default="products",
        min_length=1,
        max_length=80,
        description="Embedding collection name.",
    )
    embedding_provider: Literal["deterministic", "mock"] = Field(
        default="deterministic",
        description="Embedding provider. Phase four runs fully offline.",
    )
    embedding_model: str = Field(
        default="deterministic-hash-v1",
        min_length=1,
        max_length=100,
        description="Stable embedding model identifier.",
    )
    embedding_dimensions: int = Field(
        default=64,
        ge=8,
        le=1024,
        description="Dimensions for the deterministic embedding provider.",
    )
    retrieval_top_k: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Maximum semantic candidates before filtering.",
    )
    retrieval_score_threshold: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity for vector candidates.",
    )
    use_real_adapters: bool = Field(
        default=False,
        description="Use SQLite/Redis/vector adapters instead of in-memory adapters.",
    )
    seed_demo_data: bool = Field(
        default=True,
        description="Seed clearly marked demonstration data into a new SQLite database.",
    )
    profile_cache_ttl_seconds: int = Field(
        default=300,
        ge=1,
        le=86400,
        description="TTL for cached profiles.",
    )
    session_context_ttl_seconds: int = Field(
        default=1800,
        ge=1,
        le=86400,
        description="TTL for short-term session context.",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Reject unsupported or empty database URLs early."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("database_url must not be blank")
        if not normalized.startswith(("sqlite:", "postgresql:", "mysql:")):
            raise ValueError(
                "database_url must start with sqlite:, postgresql:, or mysql:"
            )
        return normalized

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
