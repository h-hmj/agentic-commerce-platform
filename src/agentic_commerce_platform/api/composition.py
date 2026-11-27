"""Explicit phase-four dependency composition for the API application."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agentic_commerce_platform.agents.inventory_agent import InventoryAgent
from agentic_commerce_platform.agents.marketing_agent import MarketingAgent
from agentic_commerce_platform.agents.recommendation_agent import RecommendationAgent
from agentic_commerce_platform.domain.ports import (
    CatalogRepository,
    InventoryRepository,
    MemoryStore,
    UserBehaviorRepository,
    UserProfileRepository,
    UserRepository,
    VectorStore,
)
from agentic_commerce_platform.infrastructure.cache.memory_store import InMemoryMemoryStore
from agentic_commerce_platform.infrastructure.cache.redis_client import RedisMemoryStore
from agentic_commerce_platform.infrastructure.data import (
    InMemoryCatalogRepository,
    InMemoryInventoryRepository,
    InMemoryUserBehaviorRepository,
    InMemoryUserProfileRepository,
)
from agentic_commerce_platform.infrastructure.database import DatabaseManager
from agentic_commerce_platform.infrastructure.database.repositories import (
    DatabaseCatalogRepository,
    DatabaseInventoryRepository,
    DatabaseUserBehaviorRepository,
    DatabaseUserProfileRepository,
    DatabaseUserRepository,
)
from agentic_commerce_platform.infrastructure.database.seed import seed_demo_database
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.infrastructure.vector_store import (
    DeterministicEmbeddingProvider,
    InMemoryVectorStore,
    SQLiteVectorStore,
)
from agentic_commerce_platform.orchestration.supervisor import (
    SupervisorOrchestrator,
    WorkflowRepositories,
)
from agentic_commerce_platform.services.catalog_service import CatalogService
from agentic_commerce_platform.services.embedding_service import EmbeddingService
from agentic_commerce_platform.services.memory_service import MemoryService
from agentic_commerce_platform.services.profile_service import ProfileService
from agentic_commerce_platform.services.retrieval_service import RetrievalService
from agentic_commerce_platform.services.workflow_service import WorkflowService
from agentic_commerce_platform.settings import Settings

__all__ = ["Phase4Resources", "build_phase4_resources"]

logger = logging.getLogger(__name__)


@dataclass
class Phase4Resources:
    """Runtime adapters and services composed from explicit settings."""

    catalog_repository: CatalogRepository
    inventory_repository: InventoryRepository
    behavior_repository: UserBehaviorRepository
    profile_repository: UserProfileRepository
    user_repository: UserRepository | None
    memory_store: MemoryStore
    vector_store: VectorStore
    embedding_provider: DeterministicEmbeddingProvider
    retrieval_service: RetrievalService
    profile_service: ProfileService
    catalog_service: CatalogService
    memory_service: MemoryService
    workflow_service: WorkflowService
    database: DatabaseManager | None = None


def _build_memory_store(settings: Settings) -> MemoryStore:
    """Use Redis only when enabled and importable; otherwise degrade explicitly."""
    if not settings.redis_enabled:
        return InMemoryMemoryStore()
    try:
        import redis.asyncio as redis
    except ImportError:
        logger.warning(
            "redis_enabled_but_package_missing; using InMemoryMemoryStore"
        )
        return InMemoryMemoryStore()
    try:
        client = redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
        )
        return RedisMemoryStore(
            client,
            key_prefix=settings.redis_key_prefix,
            profile_ttl_seconds=settings.profile_cache_ttl_seconds,
            session_ttl_seconds=settings.session_context_ttl_seconds,
        )
    except Exception:
        logger.warning(
            "redis_client_initialization_failed; using InMemoryMemoryStore",
            exc_info=True,
        )
        return InMemoryMemoryStore()


def build_phase4_resources(
    settings: Settings,
    llm_provider: LLMProvider,
) -> Phase4Resources:
    """Build either SQLite-backed real adapters or offline InMemory adapters."""
    database: DatabaseManager | None = None
    user_repository: UserRepository | None = None

    if settings.use_real_adapters:
        database = DatabaseManager(settings.database_url, echo=settings.database_echo)
        database.create_schema()
        if settings.seed_demo_data:
            seed_counts = seed_demo_database(database)
            logger.info("demo_data_seeded", extra={"status_code": sum(seed_counts.values())})
        catalog_repository: CatalogRepository = DatabaseCatalogRepository(database)
        inventory_repository: InventoryRepository = DatabaseInventoryRepository(database)
        behavior_repository: UserBehaviorRepository = DatabaseUserBehaviorRepository(
            database
        )
        profile_repository: UserProfileRepository = DatabaseUserProfileRepository(
            database
        )
        user_repository = DatabaseUserRepository(database)
        vector_store: VectorStore = SQLiteVectorStore(
            database,
            collection=settings.vector_collection_name,
        )
    else:
        catalog_repository = InMemoryCatalogRepository()
        inventory_repository = InMemoryInventoryRepository()
        behavior_repository = InMemoryUserBehaviorRepository()
        profile_repository = InMemoryUserProfileRepository()
        vector_store = InMemoryVectorStore()

    memory_store = _build_memory_store(settings)
    embedding_provider = DeterministicEmbeddingProvider(
        dimensions=settings.embedding_dimensions,
        model_name=settings.embedding_model,
    )
    embedding_service = EmbeddingService(embedding_provider, vector_store)
    try:
        products = catalog_repository.search(active_only=True)
        embedding_service.index_products(products)
    except Exception:
        logger.warning("initial_embedding_index_failed", exc_info=True)

    retrieval_service = RetrievalService(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        catalog_repository=catalog_repository,
        inventory_repository=inventory_repository,
        top_k=settings.retrieval_top_k,
        score_threshold=settings.retrieval_score_threshold,
    )
    profile_service = ProfileService(
        behavior_repository,
        llm_provider,
        profile_repository=profile_repository,
        memory_store=memory_store,
        cache_ttl_seconds=settings.profile_cache_ttl_seconds,
    )
    catalog_service = CatalogService(
        catalog_repository,
        llm_provider,
        retrieval_service=retrieval_service,
    )
    memory_service = MemoryService(memory_store, behavior_repository)
    recommendation_agent = RecommendationAgent(llm_provider)
    inventory_agent = InventoryAgent(inventory_repository, llm_provider)
    marketing_agent = MarketingAgent(llm_provider)
    supervisor = SupervisorOrchestrator(
        profile_agent=profile_service.agent,
        catalog_agent=catalog_service.agent,
        recommendation_agent=recommendation_agent,
        inventory_agent=inventory_agent,
        marketing_agent=marketing_agent,
        repositories=WorkflowRepositories(
            user_behavior=behavior_repository,
            catalog=catalog_repository,
            inventory=inventory_repository,
        ),
        llm_provider=llm_provider,
        settings=settings,
        logger_instance=logger,
    )
    return Phase4Resources(
        catalog_repository=catalog_repository,
        inventory_repository=inventory_repository,
        behavior_repository=behavior_repository,
        profile_repository=profile_repository,
        user_repository=user_repository,
        memory_store=memory_store,
        vector_store=vector_store,
        embedding_provider=embedding_provider,
        retrieval_service=retrieval_service,
        profile_service=profile_service,
        catalog_service=catalog_service,
        memory_service=memory_service,
        workflow_service=WorkflowService(supervisor),
        database=database,
    )
