r"""Opt-in integration test against a real local Redis service.

Run with:
    $env:RUN_REDIS_INTEGRATION = "1"
    .\.venv\Scripts\python.exe -m pytest tests/integration/test_real_redis_integration.py -q

The default suite skips this test so offline runs do not require a Redis daemon.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agentic_commerce_platform.api.app import create_app
from tests.phase4_helpers import make_real_settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REDIS_INTEGRATION") != "1",
    reason="set RUN_REDIS_INTEGRATION=1 to run against a real Redis service",
)


def test_real_redis_behavior_profile_and_ttl(tmp_path) -> None:
    """Real Redis receives behavior/profile keys with TTL and drives profile source."""
    redis_module = pytest.importorskip("redis")
    prefix = f"acp-test-{uuid4().hex}"
    settings = make_real_settings(
        tmp_path,
        redis_enabled=True,
        redis_key_prefix=prefix,
    )
    sync_client = redis_module.Redis.from_url(
        settings.redis_url.get_secret_value(),
        decode_responses=True,
    )
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            behavior = client.post(
                "/api/v1/users/u-real-redis/behaviors",
                json={
                    "behavior_type": "view",
                    "item_id": "p-001",
                    "category": "books",
                },
            )
            assert behavior.status_code == 201

            profile = client.get("/api/v1/users/u-real-redis/profile")
            assert profile.status_code == 200
            body = profile.json()
            assert body["data_source"] == "redis"
            assert body["memory_source"] == "redis"
            assert body["profile_persisted"] is True

            keys = sorted(sync_client.keys(f"{prefix}:*"))
            assert any(":behavior:u-real-redis:all" in key for key in keys)
            assert any(":behavior:u-real-redis:view" in key for key in keys)
            assert any(":profile:u-real-redis" in key for key in keys)
            assert all(sync_client.ttl(key) > 0 for key in keys)
    finally:
        keys = sync_client.keys(f"{prefix}:*")
        if keys:
            sync_client.delete(*keys)
        sync_client.close()
