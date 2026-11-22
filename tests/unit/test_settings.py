"""Tests for environment and `.env` settings loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ecommerce_platform.settings import (
    AppEnvironment,
    LogFormat,
    LogLevel,
    Settings,
)


def test_development_defaults_require_no_external_configuration(
    clean_settings_environment: None,
) -> None:
    """Defaults are usable offline and contain no secret material."""
    settings = Settings(_env_file=None)

    assert settings.app_name == "multi-agent-ecommerce-platform"
    assert settings.app_version == "0.1.0"
    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.debug is False
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.log_level is LogLevel.INFO
    assert settings.log_format is LogFormat.CONSOLE
    assert settings.llm_provider == "mock"
    assert settings.llm_api_key.get_secret_value() == ""
    assert settings.llm_base_url is None
    assert settings.llm_model == "mock-llm-v1"


def test_environment_variables_are_loaded_and_secret_is_masked(
    clean_settings_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment variables populate settings and SecretStr masks the key."""
    monkeypatch.setenv("APP_NAME", "test-ecommerce")
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    monkeypatch.setenv("APP_ENV", "TEST")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("API_PORT", "9100")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_FORMAT", "JSON")
    monkeypatch.setenv("LLM_PROVIDER", "MOCK")
    monkeypatch.setenv("LLM_API_KEY", "super-secret-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "custom-mock")

    settings = Settings(_env_file=None)

    assert settings.app_name == "test-ecommerce"
    assert settings.app_version == "9.9.9"
    assert settings.app_env is AppEnvironment.TEST
    assert settings.debug is True
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9100
    assert settings.log_level is LogLevel.DEBUG
    assert settings.log_format is LogFormat.JSON
    assert settings.llm_provider == "mock"
    assert settings.llm_api_key.get_secret_value() == "super-secret-key"
    assert str(settings.llm_base_url).rstrip("/") == "https://example.test/v1"
    assert settings.llm_model == "custom-mock"
    assert "super-secret-key" not in repr(settings)
    assert "super-secret-key" not in str(settings)


def test_dotenv_file_is_supported(
    clean_settings_environment: None,
    tmp_path: Path,
) -> None:
    """Explicit `.env` files are read without requiring a real API key."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_NAME=dotenv-app\n"
        "APP_ENV=test\n"
        "LLM_PROVIDER=mock\n"
        "LLM_MODEL=dotenv-mock\n"
        "LLM_API_KEY=\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "dotenv-app"
    assert settings.app_env is AppEnvironment.TEST
    assert settings.llm_provider == "mock"
    assert settings.llm_model == "dotenv-mock"
    assert settings.llm_api_key.get_secret_value() == ""


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"app_env": "staging"}, "app_env"),
        ({"api_port": 0}, "api_port"),
        ({"api_port": 70000}, "api_port"),
        ({"llm_provider": "openai"}, "llm_provider"),
        ({"app_env": "production", "debug": True}, "debug"),
        ({"log_level": "verbose"}, "log_level"),
        ({"log_format": "xml"}, "log_format"),
    ],
)
def test_invalid_settings_are_rejected(
    clean_settings_environment: None,
    overrides: dict[str, object],
    message: str,
) -> None:
    """Important configuration values fail fast at startup."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, **overrides)

    assert message in str(exc_info.value)
