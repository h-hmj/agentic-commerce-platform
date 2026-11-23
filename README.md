# agentic-commerce-platform

一个面向真实工程能力学习与求职展示的多 Agent 电商平台。当前仓库已经完成：

- **阶段一：工程骨架与基础设施**
- **阶段二：专业 Agent 的独立设计与实现**

当前阶段二的五个 Agent 可以独立实例化、注入依赖和测试，但**还没有 Supervisor、
LangGraph 工作流或多 Agent 自动编排**。

> **重要边界**
>
> - `POST /api/v1/recommend` 仍然是阶段一骨架，`status=skeleton`、`products=[]`。
> - 阶段二 Agent 目前通过 Service 独立调用，没有接入 API 编排。
> - 没有真实商品、库存或用户行为数据；全部是 phase-2 in-memory demo data。
> - 没有真实 LLM 调用，只使用完全离线的 `MockLLMProvider`。
> - 没有 Redis、MySQL、PostgreSQL、Milvus、Qdrant、Kafka 或 Prometheus。
> - 没有 Supervisor、LangGraph 图、RAG、长期记忆或 Human-in-the-loop。
> - MarketingAgent 只做基础敏感词检查，不声称完成完整广告法审查。

## 阶段目标

### 阶段一：工程骨架与基础设施

- 标准 Python src 项目、`pyproject.toml` 和依赖管理。
- Pydantic v2 配置、领域模型、异常体系。
- 统一日志、request_id/agent_name、`BaseAgent`。
- `LLMProvider`、离线 `MockLLMProvider`。
- FastAPI 健康检查与推荐接口骨架。
- LangGraph 状态模型预留。
- 离线单元测试和 API 集成测试。

### 阶段二：专业 Agent 的独立设计与实现

- 五个可独立运行的专业 Agent。
- Agent 专用 Pydantic 输入/输出模型。
- Repository Protocol、三个内存适配器。
- 可测试的规则：用户分群、目录过滤、规则排序、库存决策、营销文案。
- 单 Agent Service 层。
- 每个 Agent 的独立测试和阶段二集成测试。
- 阶段二架构文档。

## 当前已实现

- Python 3.11+ / `src` 布局 / `pyproject.toml`。
- 环境变量和 `.env` 配置、API Key 脱敏、配置校验。
- 项目级异常、稳定错误 JSON。
- 统一 console/JSON 日志和关联字段。
- `BaseAgent` 生命周期：计时、日志、异常转结果、超时、重试扩展点。
- 五个专业 Agent：
  - `UserProfileAgent`
  - `CatalogAgent`
  - `RecommendationAgent`
  - `InventoryAgent`
  - `MarketingAgent`
- 三个数据访问 Protocol 和内存适配器。
- 阶段二专用输入/输出模型。
- 五个独立 Service；阶段一 `RecommendationService` 保持兼容。
- 阶段一 API 健康检查和推荐骨架。
- 149 个通过的测试（含阶段一原有 67 个）。
- README、阶段一文档、阶段二架构文档。

## 五个专业 Agent

| Agent | 职责 | 输入模型 | 输出模型 |
| --- | --- | --- | --- |
| `UserProfileAgent` | 基于内存行为数据推断分群、偏好类目、价格区间 | `UserProfileInput` | `UserProfileOutput` |
| `CatalogAgent` | 关键词/类目/价格筛选，返回目录检索结果 | `CatalogInput` | `CatalogOutput` |
| `RecommendationAgent` | 按类目、价格、库存、标签和多样性进行规则排序 | `RecommendationInput` | `RecommendationOutput` |
| `InventoryAgent` | 判断可售性、低库存预警和限购建议 | `InventoryInput` | `InventoryOutput` |
| `MarketingAgent` | 基于用户分群生成安全文案并做基础敏感词检查 | `MarketingInput` | `MarketingOutput` |

### UserProfileAgent

- 名称：`user_profile_agent`
- 规则分群：`new_user`、`active`、`price_sensitive`、`high_value`、`churn_risk`。
- 输入：`user_id`、recent views/clicks/purchases、`category_counts`、
  `average_order_value`、活跃天数和账号年龄。
- 输出：`segments`、`preferred_categories`、`price_range`、`recent_interests`、
  `confidence`、`profile_source`、`explanation`、`warnings`。
- 结构化画像完全由规则生成；Mock LLM 只生成解释，不提供事实。
- 空行为数据返回 `new_user` 默认画像；Mock LLM 失败时返回
  `profile_source=rule_based` 并记录 warning。

### CatalogAgent

- 名称：`catalog_agent`
- 输入：`query`、`category`、`min_price`、`max_price`、`limit`。
- 输出：`products`、`matched_count`、`query`、`filters`、`source`。
- 支持关键词、分类、价格和组合筛选；`matched_count` 是 limit 之前的匹配总数。
- 只使用注入的 `CatalogRepository`，不实现 embedding、向量检索、RAG 或协同过滤。

### RecommendationAgent

- 名称：`recommendation_agent`
- 输入：`user_profile`、`candidate_products`、`num_items`。
- 输出：`products`、`ranking_reasons`、`strategy=rule_based_demo`、
  `filtered_count`、`confidence`。
- 规则权重：
  - 类目匹配 +30
  - 价格区间匹配 +15
  - 有库存 +5
  - 标签与兴趣匹配 +20
  - 每个类目最多 2 个商品，新类目获得多样性加成
- 重复商品和缺货商品在排序前过滤；排序按分数和 `product_id` 稳定决定。
- 不把 LLM 文本作为排序结果。

### InventoryAgent

- 名称：`inventory_agent`
- 输入：`products`、`low_stock_threshold`。
- 输出：`available_products`、`unavailable_products`、`low_stock_alerts`、
  `purchase_limits`、`unavailable_reasons`、`source`。
- `stock <= 0` 不可售；库存记录缺失也不可售；低库存生成预警和 `min(stock, 2)` 限购。
- 返回库存解析后的商品副本，不修改原始 Product。

### MarketingAgent

- 名称：`marketing_agent`
- 输入：`user_profile`、`products`、可选 `style`。
- 输出：`copies`；每个 copy 包含 `product_id`、`copy`、`style`、
  `compliance_passed`、`warnings`、`provider`。
- 风格：`welcome`、`value`、`premium`、`active`、`recall`。
- 商品事实来自真实 Product 字段和确定性模板；LLM 只允许输出安全开场语白名单，
  不会接受任意商品描述。
- Mock LLM 失败时安全回退到规则文案。
- 风险词：`国家级`、`第一`、`最好`、`绝对`、`100%`。风险词命中时
  `compliance_passed=false`。

## Repository、Agent、Service 关系

```text
Repository Protocol
  CatalogRepository / InventoryRepository / UserBehaviorRepository
        │
        ▼
Professional Agent (BaseAgent 子类)
  单次业务规则执行 + 统一 AgentResult
        │
        ▼
Service
  ProfileService / CatalogService / ProductRecommendationService /
  InventoryService / MarketingService
  只调用一个 Agent；校验专用输出；失败抛 AgentExecutionError
```

- Agent 只依赖 Protocol，不依赖具体内存实现。
- Service 通过构造函数接收 Repository 和 LLM Provider，再创建单个 Agent。
- Agent 之间不互相创建，也不共享全局变量。
- 候选商品型的 Recommendation/Marketing 由调用方传入商品，不额外隐藏数据访问。
- 所有五个 Agent 都通过构造函数接收 `LLMProvider`，保持统一依赖契约；
  Catalog、Inventory、Recommendation 的核心规则不依赖 LLM 输出。

## 内存演示数据

数据全部集中在：

```text
src/agentic_commerce_platform/infrastructure/data/demo_data.py
```

包含：

- 10 个固定的演示商品 `DEMO_PRODUCTS`。
- 独立于 `Product.stock` 的库存映射 `DEMO_INVENTORY`。
- 4 个演示用户行为记录 `DEMO_BEHAVIORS`。
- `DEMO_DATA_DISCLAIMER` 明确标记：phase-2 in-memory demo data，不是真实数据。

适配器：

- `InMemoryCatalogRepository`
- `InMemoryInventoryRepository`
- `InMemoryUserBehaviorRepository`

适配器默认加载演示数据，也支持测试时传入自定义数据。读取返回副本，避免外部修改
内部状态；目录和库存输出使用 `source=in_memory_demo`。

## 当前 Mock 与内存数据的位置

| 位置 | 用途 |
| --- | --- |
| `MockLLMProvider` | 离线解释/开场语，不调用真实模型 |
| `UserProfileAgent` | 规则画像 + Mock 解释；失败时规则降级 |
| `MarketingAgent` | 规则文案 + 可选 Mock 安全开场语 |
| `InMemoryCatalogRepository` | 集中演示商品 |
| `InMemoryInventoryRepository` | 固定演示库存 |
| `InMemoryUserBehaviorRepository` | 固定演示用户行为 |
| `RecommendationAgent` | `rule_based_demo`，不使用 LLM 排序 |

## 当前未实现

- Supervisor、LangGraph 节点/图、自动多 Agent 编排或检查点。
- 真实用户画像持久化和长期记忆。
- RAG、Embedding、向量检索、Milvus、Qdrant。
- 真实 LLM API 和完整 Prompt 管理。
- Redis、MySQL、PostgreSQL、Kafka。
- Human-in-the-loop。
- Prometheus、Agent 自动评估体系。
- 真实广告法审查、真实推荐质量评估。
- 鉴权、限流、生产部署和前端。

## 目录结构

```text
agentic-commerce-platform/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── src/
│   └── agentic_commerce_platform/
│       ├── __init__.py
│       ├── settings.py
│       ├── api/
│       │   ├── app.py
│       │   ├── dependencies.py
│       │   ├── exception_handlers.py
│       │   ├── middleware.py
│       │   └── routes/
│       │       ├── health.py
│       │       └── recommendation.py
│       ├── agents/
│       │   ├── base.py
│       │   ├── demo.py
│       │   ├── profile_agent.py
│       │   ├── catalog_agent.py
│       │   ├── recommendation_agent.py
│       │   ├── inventory_agent.py
│       │   └── marketing_agent.py
│       ├── domain/
│       │   ├── models.py
│       │   ├── agent_models.py
│       │   ├── enums.py
│       │   ├── errors.py
│       │   └── ports.py
│       ├── services/
│       │   ├── recommendation_service.py
│       │   ├── product_recommendation_service.py
│       │   ├── profile_service.py
│       │   ├── catalog_service.py
│       │   ├── inventory_service.py
│       │   ├── marketing_service.py
│       │   └── agent_runner.py
│       ├── infrastructure/
│       │   ├── data/
│       │   │   ├── demo_data.py
│       │   │   ├── in_memory_catalog.py
│       │   │   ├── in_memory_inventory.py
│       │   │   └── in_memory_user_behavior.py
│       │   ├── llm/
│       │   │   ├── base.py
│       │   │   └── mock_provider.py
│       │   └── observability/
│       │       └── logging.py
│       └── orchestration/
│           └── state.py
├── tests/
│   ├── conftest.py
│   ├── helpers.py
│   ├── unit/
│   │   ├── test_profile_agent.py
│   │   ├── test_catalog_agent.py
│   │   ├── test_recommendation_agent.py
│   │   ├── test_inventory_agent.py
│   │   ├── test_marketing_agent.py
│   │   ├── test_in_memory_catalog.py
│   │   ├── test_in_memory_inventory.py
│   │   ├── test_in_memory_user_behavior.py
│   │   ├── test_agent_contracts.py
│   │   └── ...阶段一测试
│   └── integration/
│       ├── test_api.py
│       └── test_phase2_agent_flow.py
└── docs/
    ├── architecture.md
    ├── phase-1-acceptance.md
    └── phase-2-architecture.md
```

### 结构说明

- 阶段二没有机械重排阶段一目录。
- `domain/agent_models.py` 单独承载阶段二 Agent 模型，避免污染阶段一 API 契约。
- `domain/ports.py` 定义 Repository 协议，具体实现在 infrastructure。
- `product_recommendation_service.py` 与阶段一 `recommendation_service.py` 分开，
  保证 API 兼容且不提前实现编排。
- 新增 `tests/helpers.py` 作为测试数据工厂。

## 环境要求

- Python 3.11+
- 阶段二不需要网络、真实 API Key、Redis、数据库或向量数据库。

## 安装

```powershell
cd agentic-commerce-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

POSIX：

```bash
cd agentic-commerce-platform
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## 环境变量

复制：

```powershell
Copy-Item .env.example .env
```

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `agentic-commerce-platform` | 应用名称 |
| `APP_VERSION` | `0.1.0` | 应用版本 |
| `APP_ENV` | `development` | `development` / `test` / `production` |
| `DEBUG` | `false` | 生产环境必须为 `false` |
| `API_HOST` | `127.0.0.1` | API 主机 |
| `API_PORT` | `8000` | API 端口 |
| `LOG_LEVEL` | `INFO` | 日志等级 |
| `LOG_FORMAT` | `console` | `console` 或 `json` |
| `LLM_PROVIDER` | `mock` | 阶段二仍只支持 `mock` |
| `LLM_API_KEY` | 空 | 不需要；`SecretStr` 保护 |
| `LLM_BASE_URL` | 空 | 阶段二不使用 |
| `LLM_MODEL` | `mock-llm-v1` | 未来 Provider 配置 |

## 启动

```bash
uvicorn agentic_commerce_platform.api.app:app --host 127.0.0.1 --port 8000 --reload
```

API 文档：<http://127.0.0.1:8000/docs>

## API 兼容说明

阶段一 API 保持不变：

- `GET /health`
- `POST /api/v1/recommend`，仍然返回 `status=skeleton`、`products=[]`。

健康检查示例：

```bash
curl http://127.0.0.1:8000/health
```

```json
{
  "status": "healthy",
  "app_name": "agentic-commerce-platform",
  "version": "0.1.0",
  "environment": "development"
}
```

阶段一推荐骨架请求：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: demo-request-1" \
  -d '{"user_id":"demo-user","scene":"home","num_items":3}'
```

响应仍是：

```json
{
  "request_id": "demo-request-1",
  "user_id": "demo-user",
  "status": "skeleton",
  "products": [],
  "messages": [
    "阶段一工程骨架已运行，真实推荐流程将在后续阶段实现。",
    "当前使用 DemoAgent 与 MockLLMProvider，响应不是真实商品推荐。"
  ],
  "agent_results": {
    "demo_agent": {
      "agent_name": "demo_agent",
      "success": true,
      "latency_ms": 0.2,
      "error": null,
      "confidence": null,
      "data": {
        "phase": "phase-1",
        "demo": true,
        "provider": "mock"
      }
    }
  },
  "total_latency_ms": 0.3
}
```

阶段二五个 Agent 目前不通过 API 暴露，也不新增 Supervisor 或自动编排端点。
需要单独调用时使用 Service：

```python
from agentic_commerce_platform.infrastructure.data import InMemoryCatalogRepository
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from agentic_commerce_platform.services import CatalogService
from agentic_commerce_platform.domain.agent_models import CatalogInput

service = CatalogService(InMemoryCatalogRepository(), MockLLMProvider())
result = await service.search_products(CatalogInput(query="python", limit=5))
```

## 测试

运行：

```bash
pytest -q
```

等价命令：

```bash
python -m pytest -q
```

单独运行某个 Agent 的测试：

```bash
pytest -q tests/unit/test_profile_agent.py
pytest -q tests/unit/test_catalog_agent.py
pytest -q tests/unit/test_recommendation_agent.py
pytest -q tests/unit/test_inventory_agent.py
pytest -q tests/unit/test_marketing_agent.py
pytest -q tests/unit/test_in_memory_catalog.py
pytest -q tests/unit/test_in_memory_inventory.py
pytest -q tests/unit/test_in_memory_user_behavior.py
pytest -q tests/unit/test_agent_contracts.py
```

阶段二新增测试覆盖：

- UserProfile：正常、空、新用户、活跃、价格敏感、高价值、流失、非法输入、
  Mock LLM 失败、Repository 失败。
- Catalog：关键词、分类、价格、组合、limit、无结果、空查询、非法范围、
  仓库返回值隔离。
- Recommendation：类目、价格、缺货、多样性、去重、num_items、空候选、稳定排序、
  推荐理由、不调用 LLM。
- Inventory：正常、缺货、低库存、限购、空输入、非法库存、Repository 失败。
- Marketing：五种分群风格、显式覆盖、真实商品字段、敏感词、Mock 成功、
  Mock 失败安全回退、空商品、多商品对应。
- 数据适配器：过滤正确、返回副本不修改原数据、来源标记、非法种子。
- 集成：五个 Service 在外部传入数据时独立调用；阻断出站网络；无 API Key；
  无 Redis/数据库/向量库依赖。
- 阶段一测试全部保留。

当前实际结果：

```text
149 passed, 1 warning in 0.91s
```

唯一 warning 是第三方 FastAPI/Starlette TestClient 对 httpx 的弃用提示，不是项目
测试失败。阶段一原有 67 个测试仍全部通过。完整阶段二说明见
[阶段二架构文档](docs/phase-2-architecture.md)。

### 阶段一兼容性

- 阶段一 API 路由、错误结构、Settings、日志和 `BaseAgent` 未被重写。
- 阶段一 `RecommendationService` 和 `DemoAgent` 保留。
- `/health` 和 `/api/v1/recommend` 的原有测试继续通过。
- 阶段二 Agent 通过 Service 单独调用，不改变阶段一 API 行为。

## 为什么本阶段不实现 Supervisor

Supervisor 需要跨 Agent 的状态传递、路由、失败降级和并行调度。阶段二的目标是先让
每个专业 Agent 具有稳定的输入输出、独立测试和可替换依赖。如果此时提前引入
Supervisor：

- 会把未稳定的 Agent 契约固化到编排层。
- 容易让 Agent 之间产生隐式耦合。
- 会让测试从“单 Agent 规则”变成脆弱的端到端流程测试。
- 会超出本阶段明确禁止的范围。

因此本阶段只实现单个 Agent 和单个 Service 的独立调用。未来 LangGraph 接入时，
Supervisor/节点应通过 Service 或显式状态传递协作，而不是在 Agent 内部互相调用。

## 后续阶段规划

1. **阶段三：记忆与画像持久化**：用户长期记忆、存储适配器和更新策略。
2. **阶段四：Supervisor 与 LangGraph**：图节点、路由、并行调用、状态合并、失败降级。
3. **阶段五：RAG 与库存约束**：商品知识库、向量检索、库存约束决策。
4. **阶段六：Human-in-the-loop 与营销**：人工审批、可中断工作流。
5. **阶段七：可观测性与评估**：执行轨迹、指标、评估数据集和自动回归。
6. **阶段八：生产基础设施**：数据库、Redis、向量库、消息队列、鉴权与部署。

## 设计文档

- [阶段一架构说明](docs/architecture.md)
- [阶段一验收记录](docs/phase-1-acceptance.md)
- [阶段二架构说明](docs/phase-2-architecture.md)
