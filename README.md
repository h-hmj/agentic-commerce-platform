# agentic-commerce-platform

一个面向真实工程能力学习与求职展示的多 Agent 电商平台。当前仓库已经完成：

- **阶段一：工程骨架与基础设施**
- **阶段二：专业 Agent 的独立设计与实现**
- **阶段三：Supervisor、多 Agent 协作与 LangGraph 工作流**

阶段三通过 **真实编译的 LangGraph StateGraph** 将五个专业 Agent 串成可执行流程，
并由 `SupervisorOrchestrator` 负责依赖注入、执行、错误降级和响应聚合。

> **重要边界**
>
> - 阶段三使用 phase-2 in-memory demo data，不是真实商品/库存/用户数据。
> - 当前只使用离线 `MockLLMProvider`，没有真实 LLM 调用。
> - `POST /api/v1/recommend` 仍保留阶段一 skeleton 行为，用于兼容。
> - 阶段三工作流接口是 `POST /api/v1/workflow/recommend`。
> - 没有 Redis、MySQL、PostgreSQL、Milvus、Qdrant、Kafka 或 Prometheus。
> - 没有 Embedding、RAG、真实支付/订单/WMS、Human-in-the-loop。
> - 没有 Checkpoint 持久化、多轮会话记忆或生产级分布式部署。
> - MarketingAgent 只做基础敏感词检查，不声称完成完整广告法审查。

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
- 阶段一 skeleton API 继续兼容。
- 203 个测试通过。

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
4. 执行 `graph.ainvoke()`。
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

启动：

```bash
uvicorn agentic_commerce_platform.api.app:app --host 127.0.0.1 --port 8000 --reload
```

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
  "llm_provider": "mock",
  "messages": [
    "阶段三工作流使用 phase-2 in-memory demo data 与 MockLLMProvider，结果不是真实线上推荐。"
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

数据不是真实商品、库存或客户数据。工作流响应显式返回
`data_source=in_memory_demo`、`llm_provider=mock` 和 demo 说明。

## 当前未实现

- Checkpoint 持久化、多轮会话记忆、HITL。
- 真实数据库、Redis、向量数据库、Kafka、Prometheus。
- Embedding、RAG、协同过滤。
- 真实 LLM API 和完整 Prompt 管理。
- 真实订单、支付、WMS。
- 真实广告法审查、生产级推荐质量评估。
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
│   └── regression/
│       └── test_phase1_phase2_compatibility.py
└── docs/
    ├── architecture.md
    ├── phase-1-acceptance.md
    ├── phase-2-architecture.md
    └── phase-3-architecture.md
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
- 阶段一/二回归。

当前实际结果：

```text
203 passed, 1 warning in 2.91s
```

唯一 warning 是第三方 FastAPI/Starlette TestClient 对 httpx 的弃用提示，不是项目
测试失败。阶段一/二原有 149 个测试继续通过；阶段三新增 54 个测试。

## 设计决策

- LangGraph 使用原生 fan-out/fan-in，不手工 `asyncio.gather`。
- 状态 reducer 只用于并行写入字段，避免状态覆盖。
- Supervisor 只编排，不承载规则。
- 阶段一 `/recommend` 保留 skeleton，新增独立工作流 API，避免破坏兼容。
- 失败而不是空列表：错误写入 errors/warnings 和 agent_results，不能静默降级。
- 库存失败绝不默认有货。
- 营销文案只接受最终可售商品，响应再次校验。
- 不提前实现 Checkpoint、Redis、数据库、RAG、真实 LLM。

## 后续阶段规划

1. **阶段四：Checkpoint 与真实数据适配器**：LangGraph checkpointer、数据库/Redis、
   仓储替换、幂等执行。
2. **阶段五：RAG 与真实检索**：Embedding、向量库、检索端口和评估。
3. **阶段六：HITL 与运营能力**：人工审批、可中断工作流、真实营销合规。
4. **阶段七：可观测性与评估**：OpenTelemetry、Prometheus、执行轨迹、自动评估。
5. **阶段八：生产部署**：鉴权、限流、部署、分布式调度。

## 设计文档

- [阶段一架构说明](docs/architecture.md)
- [阶段一验收记录](docs/phase-1-acceptance.md)
- [阶段二架构说明](docs/phase-2-architecture.md)
- [阶段三架构说明](docs/phase-3-architecture.md)
