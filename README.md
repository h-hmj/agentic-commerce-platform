# agentic-commerce-platform

一个面向真实工程能力学习与求职展示的多 Agent 电商平台。当前仓库已经完成：

- **阶段一：工程骨架与基础设施**
- **阶段二：专业 Agent 的独立设计与实现**
- **阶段三：Supervisor、多 Agent 协作与 LangGraph 工作流**
- **阶段四：真实数据检索、RAG、用户画像持久化与记忆**

阶段三通过 **真实编译的 LangGraph StateGraph** 将五个专业 Agent 串成可执行流程，
并由 `SupervisorOrchestrator` 负责依赖注入、执行、错误降级和响应聚合。阶段四在
保持该拓扑不变的前提下加入 SQLite/SQLAlchemy 持久化、Redis/InMemory 记忆、确定性
本地 Embedding、向量检索和画像持久化。

> **重要边界**
>
> - 默认 `USE_REAL_ADAPTERS=false`，测试使用 in-memory 适配器；打开后使用 SQLite。
> - SQLite 初始数据是明确标记的演示数据，不是真实生产商品/库存/用户数据。
> - 当前只使用离线 `MockLLMProvider`，没有真实 LLM 调用。
> - `POST /api/v1/recommend` 仍保留阶段一 skeleton 行为，用于兼容。
> - 阶段三工作流接口是 `POST /api/v1/workflow/recommend`。
> - Redis 适配器已在本机真实 Redis 服务上验证（PING、key 前缀、TTL、行为/画像/
>   session 往返）。默认测试不依赖 Redis；真实集成测试通过
>   `RUN_REDIS_INTEGRATION=1` 显式开启。Redis 不可用时显式降级，不伪造写入成功。
> - 本地 RAG 使用确定性哈希 Embedding 和进程内/SQLite 向量索引，不是生产语义检索。
> - 没有真实支付/订单/WMS、Human-in-the-loop、完整 Agent 评估平台或分布式部署。
> - MarketingAgent 只做基础敏感词检查，不声称完成完整广告法审查。
>
> 详细设计、数据优先级和未验证项见
> [阶段四架构](docs/phase-4-architecture.md)。

## 阶段目标

### 阶段一：工程骨架与基础设施

- 标准 Python src 项目、`pyproject.toml`、Pydantic v2 配置和领域模型。
- 项目级异常、统一日志、`BaseAgent`、`LLMProvider`、`MockLLMProvider`。
- FastAPI 健康检查与推荐骨架。
- 单元测试和 API 集成测试。

### 阶段二：专业 Agent

- `UserProfileAgent`
- `CatalogAgent`
- `RecommendationAgent`
- `InventoryAgent`
- `MarketingAgent`
- Repository Protocol、三个内存适配器、单 Agent Service 层。
- 规则画像、规则检索、规则排序、库存决策、营销文案和独立测试。

### 阶段三：多 Agent 协作

- 真实 LangGraph `StateGraph`、节点、条件边、编译图。
- Supervisor 显式注入五个 Agent、Repository、LLM、Settings、logger。
- 用户画像和商品目录并行，推荐节点等待两个分支汇聚。
- 推荐 → 库存 → 库存过滤 → 营销 → 聚合。
- 状态 reducer、AgentResult 保留、失败/空结果/全缺货处理。
- 新工作流 API 和端到端测试。

## 当前已实现

- Python 3.11+ / `src` 布局 / `pyproject.toml`。
- Pydantic v2 配置、领域模型、异常体系。
- 统一 console/JSON 日志、request_id/agent_name。
- `BaseAgent` 生命周期、超时、重试扩展点。
- 五个阶段二专业 Agent。
- 阶段三 LangGraph 工作流：
  - 8 个节点。
  - profile/catalog 并行。
  - 条件路由与安全失败路径。
  - Supervisor 依赖注入与图执行。
  - 最终响应聚合。
- 三个内存 Repository 和集中演示数据。
- 阶段四 SQLAlchemy 2.x 数据层：商品、库存、用户、行为、画像、向量表。
- Redis/InMemory 记忆适配器、确定性 Embedding、本地向量索引和 RAG。
- 画像持久化、缓存、实时行为优先级与降级警告。
- 阶段一 skeleton API 继续兼容。
- 全部测试通过；具体数量见 [阶段四验收](docs/phase-4-acceptance.md)。

## 阶段四快速开始

```bash
# 1. 安装依赖
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 2. 可选：复制配置并启用 SQLite 真实适配器
Copy-Item .env.example .env
# 编辑 .env: USE_REAL_ADAPTERS=true

# 3. 应用数据库迁移
.\.venv\Scripts\python.exe -m alembic upgrade head

# 4. 启动（必须使用虚拟环境解释器，避免全局 uvicorn）
.\.venv\Scripts\python.exe -m uvicorn agentic_commerce_platform.api.app:app --host 127.0.0.1 --port 8000 --reload
```

阶段四新增接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/catalog/search` | 结构化 + 可选 RAG 商品搜索 |
| `POST` | `/api/v1/retrieval/search` | 返回 RAG 候选、分数、来源 |
| `GET` | `/api/v1/users/{user_id}/profile` | 读取/构建持久画像 |
| `POST` | `/api/v1/users/{user_id}/behaviors` | 写入行为事件 |

离线默认模式不写数据库；`USE_REAL_ADAPTERS=true` 时使用
`data/agentic_commerce.db`（或 `DATABASE_URL`），并在数据库为空时按
`SEED_DEMO_DATA` 写入演示数据。

## 阶段三架构

```text
Client
  │ POST /api/v1/workflow/recommend
  ▼
WorkflowService
  │ 只委托 Supervisor，不编排 Agent
  ▼
SupervisorOrchestrator
  │ 注入 5 个 Agent + Repository bundle + MockLLMProvider + Settings + logger
  │ 创建初始 state，执行编译后的 LangGraph
  ▼
initialize_request
  ├── user_profile ──┐
  └── catalog ───────┴──> recommendation
                              │
                              ├──> inventory → inventory_filter → marketing
                              │                        │
                              └────────────────────────┴──> aggregate → END
```

### Supervisor 职责

`SupervisorOrchestrator`：

1. 接收统一的 `RecommendationRequest`。
2. 创建带 request ID 的初始 `RecommendationWorkflowState`。
3. 用注入的五个 Agent 构建节点和 LangGraph。
4. 使用 `graph.astream(..., stream_mode="values")` 执行并保留最近成功快照。
5. 捕获图级未知异常，写入安全失败状态。
6. 聚合最终状态并转换为 `WorkflowRecommendationResponse`。

Supervisor 不实现任何业务规则，也不创建隐藏的全局 Agent。五个 Agent 均由应用工厂
显式创建并注入。

### LangGraph 节点

| 节点 | 职责 |
| --- | --- |
| `initialize_request` | 生成/确认 request_id、初始化时间、状态、结果集合 |
| `user_profile` | 调用 UserProfileAgent，失败时使用显式默认画像 |
| `catalog` | 根据 context 构造查询，调用 CatalogAgent |
| `recommendation` | 等待并行分支汇聚，调用 RecommendationAgent |
| `inventory` | 调用 InventoryAgent；失败时不得假设有货 |
| `inventory_filter` | 按推荐顺序过滤不可售商品 |
| `marketing` | 只对库存过滤后的商品生成文案 |
| `aggregate` | 计算总耗时、最终状态和商品数 |

节点通过 `Agent.run(request=...)` 调用 Agent，验证 `AgentResult.success` 和专用
Pydantic 输出模型；不直接相信字典，也不互相调用 Agent。

### 工作流状态

`RecommendationWorkflowState` 位于
`src/agentic_commerce_platform/orchestration/state.py`。

核心字段：

- 请求：`request_id`、`user_id`、`scene`、`num_items`、`context`
- 输入/中间结果：`user_profile_input`、`user_profile`、`catalog_input`、
  `candidate_products`、`recommendation_input`、`ranked_products`、
  `inventory_input`、`available_products`、`unavailable_products`、
  `inventory_alerts`、`marketing_input`、`marketing_copies`
- 可观测性：`agent_results`、`errors`、`warnings`、`current_node`、
  `workflow_status`、`failed_stage`、`started_at`、`completed_at`、
  `total_latency_ms`、`final_product_count`

并行字段使用 reducer：

- `agent_results`: 合并 profile/catalog 两个 AgentResult。
- `errors`: 按顺序去重合并。
- `warnings`: 按顺序去重合并。

其他状态字段只有一个写入者，避免并行覆盖。

### 并行执行

`initialize_request` 同时连接到 `user_profile` 和 `catalog`。两个节点在同一
LangGraph 并发 superstep 中运行，并且都连接到 `recommendation`，因此推荐节点会等待
两者完成。

未使用手工 `asyncio.gather`。并行由 LangGraph 图调度完成；测试使用两个带延迟的
注入 Agent 验证实际并发重叠。

### 数据流

```text
request.context → CatalogInput
user request → UserProfileInput
UserProfileOutput + candidate_products → RecommendationInput
RecommendationOutput.products → InventoryInput
InventoryOutput.available_products → 按 ranked order 过滤
filtered products → MarketingInput
marketing copies → final products only
所有 AgentResult/errors/warnings → aggregate → WorkflowRecommendationResponse
```

Agent 间没有直接调用，也没有全局通信；数据全部通过 LangGraph state 和显式节点输入
传递。

## 工作流响应

新增 `WorkflowRecommendationResponse`：

- `request_id`
- `user_id`
- `status`
- `workflow_status`
- `products`
- `marketing_copies`
- `unavailable_products`
- `inventory_alerts`
- `agent_results`
- `errors`
- `warnings`
- `total_latency_ms`
- `data_source=in_memory_demo`
- `llm_provider=mock`
- `messages`

`products` 是推荐结果经库存过滤后的顺序；缺货商品不会进入。Marketing copy 只能引用
最终 products。阶段一 `RecommendationResponse` 和 `/api/v1/recommend` 保持兼容。

## 错误和降级策略

| 失败 Agent | 安全降级 |
| --- | --- |
| UserProfileAgent | 显式默认画像，记录失败结果和 warning，继续推荐 |
| CatalogAgent | 候选为空，记录 error，跳过推荐，不伪造商品 |
| RecommendationAgent | ranked 为空，记录 error，不透传未排序候选 |
| InventoryAgent | available 为空，记录 error，跳过营销，不假设有货 |
| MarketingAgent | 保留商品和库存结果，文案为空，记录 error |
| 输出 Pydantic 校验失败 | 记录 `*_output_invalid`，不信任 AgentResult.data |
| 图级未知异常 | 通过 LangGraph 状态流保留最后成功快照的 `agent_results`/`errors`/`warnings`，追加 `workflow_execution_failed`，完整堆栈只进日志 |

状态区分：

- `success`：最终商品非空，无 errors/warnings。
- `partial_success`：有商品但存在失败/降级，或空目录/全缺货等可恢复空结果。
- `failed`：没有最终商品且存在明确错误，或图执行失败。

空商品列表和工具失败不会被混为一谈。

## 五个专业 Agent

| Agent | 职责 | 输入 | 输出 |
| --- | --- | --- | --- |
| `UserProfileAgent` | 规则分群、偏好、价格区间 | `UserProfileInput` | `UserProfileOutput` |
| `CatalogAgent` | 关键词/类目/价格筛选 | `CatalogInput` | `CatalogOutput` |
| `RecommendationAgent` | 规则排序与多样性 | `RecommendationInput` | `RecommendationOutput` |
| `InventoryAgent` | 可售性、低库存、限购 | `InventoryInput` | `InventoryOutput` |
| `MarketingAgent` | 安全营销文案 | `MarketingInput` | `MarketingOutput` |

阶段二规则保持原样：

- UserProfile 支持 `new_user`、`active`、`price_sensitive`、`high_value`、
  `churn_risk`；LLM 只解释，不提供画像事实。
- Recommendation 使用确定性规则：类目 +30、价格 +15、库存 +5、标签 +20，
  每类目最多 2 个商品并应用多样性加成。
- Inventory 将 `stock<=0` 和缺失库存视为不可售，低库存生成限购。
- Marketing 商品事实来自真实字段；LLM 只允许安全开场语白名单。

## API

启动时请使用当前虚拟环境的 Python，而不是直接调用可能来自全局 PATH 的 `uvicorn`：

```powershell
.\.venv\Scripts\python.exe -m uvicorn agentic_commerce_platform.api.app:app --host 127.0.0.1 --port 8000 --reload
```

激活虚拟环境后也可以：

```powershell
python -m uvicorn agentic_commerce_platform.api.app:app --host 127.0.0.1 --port 8000 --reload
```

如果直接运行 `uvicorn` 报：

```text
ModuleNotFoundError: No module named 'agentic_commerce_platform'
```

通常说明该命令解析到了全局 Python 的 `uvicorn.exe`。当前项目的 `.venv` 使用
`--system-site-packages` 时可能没有自己的 `uvicorn.exe`。使用上面的
`python -m uvicorn` 即可确保使用虚拟环境的解释器和已安装的 editable 包。

文档：<http://127.0.0.1:8000/docs>

### 阶段三工作流接口

```bash
curl -X POST http://127.0.0.1:8000/api/v1/workflow/recommend \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: workflow-demo-1" \
  -d '{
    "user_id": "u-demo-001",
    "scene": "home",
    "num_items": 3,
    "context": {"keywords": ["python"], "locale": "zh-CN"}
  }'
```

响应示意（为简洁省略部分 `AgentResult` 的 `latency_ms`/`data` 字段）：

```json
{
  "request_id": "workflow-demo-1",
  "user_id": "u-demo-001",
  "status": "success",
  "workflow_status": "success",
  "products": [
    {
      "product_id": "p-001",
      "name": "Python 编程实战",
      "category": "books",
      "price": "89.00",
      "stock": 12,
      "tags": ["python", "programming", "backend"]
    }
  ],
  "marketing_copies": [
    {
      "product_id": "p-001",
      "copy": "精选books类目商品 Python 编程实战，售价 ¥89.00，适合注重品质体验的你。",
      "style": "premium",
      "compliance_passed": true,
      "warnings": [],
      "provider": "rule_based"
    }
  ],
  "unavailable_products": [],
  "inventory_alerts": [],
  "agent_results": {
    "user_profile_agent": {"agent_name": "user_profile_agent", "success": true},
    "catalog_agent": {"agent_name": "catalog_agent", "success": true},
    "recommendation_agent": {"agent_name": "recommendation_agent", "success": true},
    "inventory_agent": {"agent_name": "inventory_agent", "success": true},
    "marketing_agent": {"agent_name": "marketing_agent", "success": true}
  },
  "errors": [],
  "warnings": [],
  "total_latency_ms": 10.5,
  "data_source": "in_memory_demo",
  "retrieval_source": "in_memory_demo",
  "embedding_provider": "deterministic",
  "memory_source": null,
  "llm_provider": "mock",
  "messages": [
    "结果使用配置的数据适配器与 MockLLMProvider；不是真实线上推荐。"
  ]
}
```

### 阶段一兼容接口

- `GET /health` 继续工作。
- `POST /api/v1/recommend` 继续返回阶段一 `status=skeleton`、空 products。
- 原有阶段一 API 测试全部保留并通过。

## 当前 Mock 与内存数据的位置

| 位置 | 用途 |
| --- | --- |
| `MockLLMProvider` | 离线解释/安全开场语，无网络 |
| `UserProfileAgent` | 规则画像 + Mock 解释 |
| `MarketingAgent` | 规则文案 + 可选 Mock 安全开场语 |
| `InMemoryCatalogRepository` | 固定演示商品 |
| `InMemoryInventoryRepository` | 固定演示库存 |
| `InMemoryUserBehaviorRepository` | 固定演示用户行为 |
| `infrastructure/data/demo_data.py` | 集中 phase-2 in-memory demo data |
| `infrastructure/database/` | SQLAlchemy 表、Repository、种子和迁移入口 |
| `infrastructure/cache/` | Redis/InMemory 记忆适配器 |
| `infrastructure/vector_store/` | 确定性 Embedding 和本地向量索引 |

默认离线模式返回 `data_source=in_memory_demo`；`USE_REAL_ADAPTERS=true` 时返回
`data_source=database`。RAG 和画像来源分别通过 `retrieval_source`、`memory_source`
和 `profile_source` 显式暴露。

## 当前未实现

- 真实 LLM API 和完整 Prompt 管理。
- Redis 集群/故障注入、PostgreSQL/MySQL 服务的集成测试与集群部署。
- 生产级向量数据库、语义 Embedding 模型和检索质量评估。
- HITL、Checkpoint 持久化、多轮完整对话管理。
- Prometheus/OpenTelemetry 平台、Kafka、真实订单/支付/WMS。
- 真实广告法审查、鉴权、限流、生产部署和前端。

## 目录结构

```text
agentic-commerce-platform/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── src/
│   └── agentic_commerce_platform/
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
│       │   ├── agent_runner.py
│       │   ├── recommendation_service.py
│       │   ├── product_recommendation_service.py
│       │   ├── profile_service.py
│       │   ├── catalog_service.py
│       │   ├── inventory_service.py
│       │   ├── marketing_service.py
│       │   └── workflow_service.py
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
│           ├── state.py
│           ├── nodes.py
│           ├── routing.py
│           ├── graph.py
│           ├── supervisor.py
│           ├── models.py
│           └── errors.py
├── tests/
│   ├── conftest.py
│   ├── helpers.py
│   ├── workflow_helpers.py
│   ├── unit/
│   │   ├── test_workflow_state.py
│   │   ├── test_workflow_nodes.py
│   │   ├── test_workflow_routing.py
│   │   ├── test_supervisor.py
│   │   └── ...阶段一/二测试
│   ├── integration/
│   │   ├── test_api.py
│   │   ├── test_langgraph_workflow.py
│   │   ├── test_end_to_end_recommendation.py
│   │   ├── test_workflow_failures.py
│   │   ├── test_workflow_observability.py
│   │   └── test_phase2_agent_flow.py
│   ├── regression/
│   │   ├── test_phase1_phase2_compatibility.py
│   │   └── test_phase3_compatibility_after_phase4.py
│   └── phase4_helpers.py
├── migrations/
│   ├── env.py
│   └── versions/0001_phase4_initial.py
└── docs/
    ├── architecture.md
    ├── phase-1-acceptance.md
    ├── phase-2-architecture.md
    ├── phase-3-architecture.md
    ├── phase-4-architecture.md
    └── phase-4-acceptance.md
```

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

阶段三新增依赖只有 `langgraph>=1.2,<2.0`，当前验证版本为 `1.2.9`。
没有新增 LangChain 高层扩展、数据库或向量库依赖。

## 环境变量

复制：

```powershell
Copy-Item .env.example .env
```

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `agentic-commerce-platform` | 应用名称 |
| `APP_VERSION` | `0.1.0` | 版本 |
| `APP_ENV` | `development` | 运行环境 |
| `DEBUG` | `false` | 生产必须为 false |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | API 地址 |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `console` | 日志 |
| `LLM_PROVIDER` | `mock` | 阶段三仍仅支持 mock |
| `LLM_API_KEY` | 空 | 不需要；不记录 |
| `LLM_MODEL` | `mock-llm-v1` | Mock 模型标识 |

## 测试

```bash
python -m pytest -q
```

阶段三新增测试文件：

```text
tests/unit/test_workflow_state.py
tests/unit/test_workflow_nodes.py
tests/unit/test_workflow_routing.py
tests/unit/test_supervisor.py
tests/integration/test_langgraph_workflow.py
tests/integration/test_end_to_end_recommendation.py
tests/integration/test_workflow_failures.py
tests/integration/test_workflow_observability.py
tests/regression/test_phase1_phase2_compatibility.py
```

覆盖：

- 状态 reducer、初始字段、无敏感配置。
- 8 个节点独立执行。
- 条件路由：成功、空结果、失败、跳过营销。
- Supervisor 注入、完整执行、状态响应。
- 编译图节点/边。
- 并行实际重叠、并行失败结果保留。
- 各 Agent 失败、输出校验失败、未知图异常。
- 用户画像影响排序、显式状态数据流、库存过滤、文案对应。
- 工作流 API 成功、422、失败响应、无网络。
- 阶段一/二/三回归。
- 阶段四数据库、记忆、Embedding、RAG、画像持久化、API 和迁移测试。

当前实际结果：

```text
237 passed, 1 skipped, 1 warning
```

唯一 warning 是第三方 FastAPI/Starlette TestClient 对 httpx 的弃用提示，不是项目
测试失败。被跳过的 1 个测试是可选真实 Redis 集成测试。

本机已实际验证真实 Redis：

```powershell
$env:RUN_REDIS_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -q
# 238 passed, 1 warning
```

默认套件不要求 Redis/PostgreSQL/外部向量库。

## 设计决策

- LangGraph 使用原生 fan-out/fan-in，不手工 `asyncio.gather`。
- 状态 reducer 只用于并行写入字段，避免状态覆盖。
- Supervisor 只编排，不承载规则。
- 阶段一 `/recommend` 保留 skeleton，新增独立工作流 API，避免破坏兼容。
- 失败而不是空列表：错误写入 errors/warnings 和 agent_results，不能静默降级。
- 库存失败绝不默认有货。
- 营销文案只接受最终可售商品，响应再次校验。
- 相似度只作为 RAG 召回和规则排序的辅助信号，不替代 RecommendationAgent。
- Redis 故障显式降级并记录警告，不伪造缓存写入成功。
- 默认测试离线；真实 SQLite 使用隔离临时数据库。

## 后续阶段规划

1. **阶段五：HITL 与运营能力**：人工审批、可中断工作流、真实营销合规。
2. **阶段六：可观测性与评估**：OpenTelemetry、Prometheus、执行轨迹、自动评估。
3. **阶段七：生产部署**：鉴权、限流、异步数据库、Redis/向量集群和分布式调度。

## 设计文档

- [阶段一架构说明](docs/architecture.md)
- [阶段一验收记录](docs/phase-1-acceptance.md)
- [阶段二架构说明](docs/phase-2-architecture.md)
- [阶段三架构说明](docs/phase-3-architecture.md)
- [阶段四架构说明](docs/phase-4-architecture.md)
- [阶段四验收记录](docs/phase-4-acceptance.md)
