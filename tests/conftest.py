"""Shared pytest fixtures for phase-one tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ecommerce_platform.api.app import create_app
from ecommerce_platform.settings import Settings

SETTINGS_ENVIRONMENT_KEYS = (
    "APP_NAME",
    "APP_VERSION",
    "APP_ENV",
    "DEBUG",
    "API_HOST",
    "API_PORT",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
)


@pytest.fixture
def clean_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ambient configuration so settings tests are deterministic."""
    for key in SETTINGS_ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def test_settings() -> Settings:
    """Return explicit test settings that require no external services."""
    return Settings(
        _env_file=None,
        app_name="multi-agent-ecommerce-platform",
        app_version="0.1.0",
        app_env="test",
        debug=False,
        api_host="127.0.0.1",
        api_port=8000,
        log_level="WARNING",
        log_format="console",
        llm_provider="mock",
        llm_api_key="",
        llm_base_url=None,
        llm_model="mock-llm-v1",
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    """Build an isolated application with explicit test configuration."""
    return create_app(test_settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Return a synchronous HTTP client for API integration tests."""
    with TestClient(app) as test_client:
        yield test_client
