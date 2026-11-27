"""Public response contract for the phase-three recommendation workflow."""

from __future__ import annotations

from pydantic import Field, model_validator

from agentic_commerce_platform.domain.agent_models import LowStockAlert, MarketingCopy
from agentic_commerce_platform.domain.enums import (
    DataSource,
    RecommendationStatus,
    WorkflowStatus,
)
from agentic_commerce_platform.domain.models import (
    AgentResult,
    PlatformModel,
    Product,
)

__all__ = ["WorkflowRecommendationResponse"]


class WorkflowRecommendationResponse(PlatformModel):
    """Aggregated result of the LangGraph multi-agent recommendation workflow.

    This model is separate from the phase-one ``RecommendationResponse``. The
    original skeleton endpoint remains available and unchanged.
    """

    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    status: RecommendationStatus
    workflow_status: WorkflowStatus
    products: list[Product] = Field(default_factory=list)
    marketing_copies: list[MarketingCopy] = Field(default_factory=list)
    unavailable_products: list[Product] = Field(default_factory=list)
    inventory_alerts: list[LowStockAlert] = Field(default_factory=list)
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    total_latency_ms: float = Field(ge=0.0)
    data_source: DataSource = DataSource.IN_MEMORY_DEMO
    retrieval_source: str | None = Field(default=None, max_length=64)
    embedding_provider: str | None = Field(default=None, max_length=100)
    memory_source: str | None = Field(default=None, max_length=32)
    llm_provider: str = Field(default="mock", min_length=1, max_length=32)
    messages: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_consistency(self) -> WorkflowRecommendationResponse:
        """Keep final products, copies, and inventory outcomes consistent."""
        product_ids = [product.product_id for product in self.products]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("final products must be unique")

        unavailable_ids = {
            product.product_id for product in self.unavailable_products
        }
        if set(product_ids) & unavailable_ids:
            raise ValueError("available and unavailable products must be disjoint")

        unknown_copy_ids = {
            copy.product_id for copy in self.marketing_copies
        } - set(product_ids)
        if unknown_copy_ids:
            raise ValueError("marketing copies must reference final products only")

        return self
