"""End-to-end phase-four API tests against an isolated SQLite database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agentic_commerce_platform.api.app import create_app
from tests.phase4_helpers import make_real_settings


def test_real_database_catalog_rag_profile_behavior_and_workflow(tmp_path) -> None:
    """All phase-four APIs work offline with SQLite and no Redis/vector service."""
    settings = make_real_settings(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

        catalog = client.post(
            "/api/v1/catalog/search",
            json={"query": "python", "category": "books", "limit": 3},
        )
        assert catalog.status_code == 200
        catalog_body = catalog.json()
        assert catalog_body["source"] == "database"
        assert catalog_body["retrieval_source"] in {"vector", "fallback"}
        assert catalog_body["products"]

        retrieval = client.post(
            "/api/v1/retrieval/search",
            json={"query": "python 编程", "top_k": 3},
        )
        assert retrieval.status_code == 200
        retrieval_body = retrieval.json()
        assert retrieval_body["candidates"]
        assert all(0.0 <= item["score"] <= 1.0 for item in retrieval_body["candidates"])

        profile = client.get("/api/v1/users/u-demo-001/profile")
        assert profile.status_code == 200
        profile_body = profile.json()
        assert profile_body["data_source"] == "database"
        assert profile_body["profile_persisted"] is True
        assert profile_body["segments"]

        behavior = client.post(
            "/api/v1/users/u-live-test/behaviors",
            json={
                "behavior_type": "view",
                "item_id": "p-001",
                "category": "books",
                "metadata": {"source": "test"},
            },
        )
        assert behavior.status_code == 201
        assert behavior.json()["user_id"] == "u-live-test"

        live_profile = client.get("/api/v1/users/u-live-test/profile")
        assert live_profile.status_code == 200
        live_body = live_profile.json()
        assert live_body["memory_source"] == "in_memory"
        assert live_body["data_source"] == "in_memory"

        workflow = client.post(
            "/api/v1/workflow/recommend",
            json={
                "user_id": "u-demo-001",
                "scene": "home",
                "num_items": 3,
                "context": {"keywords": ["python"], "category": "books"},
            },
        )
        assert workflow.status_code == 200
        workflow_body = workflow.json()
        assert workflow_body["workflow_status"] == "success"
        assert workflow_body["data_source"] == "database"
        assert workflow_body["products"]
        assert workflow_body["retrieval_source"] in {"vector", "fallback"}
        assert workflow_body["embedding_provider"] == "deterministic"
        assert set(workflow_body["agent_results"]) >= {
            "user_profile_agent",
            "catalog_agent",
            "recommendation_agent",
            "inventory_agent",
            "marketing_agent",
        }

        skeleton = client.post(
            "/api/v1/recommend",
            json={"user_id": "u-demo-001", "scene": "home"},
        )
        assert skeleton.status_code == 200
        assert skeleton.json()["status"] == "skeleton"
        assert skeleton.json()["products"] == []

        invalid_catalog = client.post(
            "/api/v1/catalog/search",
            json={"query": "python", "min_price": "100", "max_price": "10"},
        )
        assert invalid_catalog.status_code == 422
        assert client.post("/api/v1/retrieval/search", json={"query": ""}).status_code == 422
        assert (
            client.post(
                "/api/v1/users/u-test/behaviors",
                json={"behavior_type": "unknown"},
            ).status_code
            == 422
        )


def test_offline_app_uses_in_memory_adapters_and_rag(tmp_path) -> None:
    """The default offline app still exposes catalog/RAG without touching SQLite."""
    settings = make_real_settings(tmp_path, use_real_adapters=False)
    app = create_app(settings)

    with TestClient(app) as client:
        catalog = client.post("/api/v1/catalog/search", json={"query": "python"})
        assert catalog.status_code == 200
        assert catalog.json()["source"] == "in_memory_demo"

        retrieval = client.post("/api/v1/retrieval/search", json={"query": "python"})
        assert retrieval.status_code == 200
        assert retrieval.json()["candidates"]
