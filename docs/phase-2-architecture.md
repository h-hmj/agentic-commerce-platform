# 阶段二架构说明：专业 Agent 的独立设计与实现

## 1. 范围与边界

阶段二在阶段一基础设施之上新增五个可独立运行的专业 Agent：

1. `UserProfileAgent`
2. `CatalogAgent`
3. `RecommendationAgent`
4. `InventoryAgent`
5. `MarketingAgent`

本阶段只解决“单个 Agent 如何被清晰设计、注入依赖、独立测试和通过 Service 调用”的问题。
**没有 Supervisor、LangGraph 图、多 Agent 自动编排、RAG、真实 LLM、真实数据库或向量库。**
阶段一 API `/api/v1/recommend` 仍然是 `skeleton`，没有被改造成多 Agent 流程。

项目仓库统一命名为 `agentic-commerce-platform`，Python 导入包为
`agentic_commerce_platform`。本文中的类名和协议名均以实际代码为准。

## 2. 分层结构

```text
FastAPI routes (stage-one API only)
        │
        ▼
Service layer
  ProfileService / CatalogService / ProductRecommendationService
  InventoryService / MarketingService
        │  每个 Service 只调用一个 Agent
        ▼
Professional Agents (all inherit BaseAgent)
  UserProfileAgent / CatalogAgent / RecommendationAgent
  InventoryAgent / MarketingAgent
        │
        ├── Domain ports: CatalogRepository / InventoryRepository /
        │                 UserBehaviorRepository
        ├── In-memory adapters: InMemoryCatalogRepository /
        │                       InMemoryInventoryRepository /
        │                       InMemoryUserBehaviorRepository
        ├── Phase-2 demo data: infrastructure/data/demo_data.py
        └── LLMProvider: MockLLMProvider only
```

阶段一结构保持不变，新增文件采用增量方式加入：

- `domain/agent_models.py`：阶段二输入、输出和中间模型。
- `domain/ports.py`：Agent 依赖的数据访问协议。
- `agents/*_agent.py`：五个独立专业 Agent。
- `infrastructure/data/`：集中演示数据及三个内存适配器。
- `services/{profile,catalog,inventory,marketing}_service.py`：单 Agent 服务。
- `services/product_recommendation_service.py`：阶段二推荐服务。
- `services/recommendation_service.py`：阶段一 API skeleton 服务保持不动。
- `tests/unit/test_*_agent.py`、`tests/unit/test_in_memory_*.py`、
  `tests/integration/test_phase2_agent_flow.py`：新增测试。

### 命名与兼容性决策

阶段一已经存在 `RecommendationService` 并支撑公开 API，因此阶段二不重写它，而是新增
`ProductRecommendationService`。这样：

- 阶段一 API 与原有测试保持兼容。
- 阶段二排序 Agent 可以被独立调用。
- API 层不会悄悄变成多 Agent 编排入口。

## 3. 五个专业 Agent

### 3.1 UserProfileAgent

- 稳定名称：`user_profile_agent`
- 输入：`UserProfileInput`
  - `user_id`
  - `recent_views`、`recent_clicks`、`recent_purchases`
  - `category_counts`
  - `average_order_value`
  - `days_since_last_active`、`account_age_days`（用于活跃/流失判断）
- 输出：`UserProfileOutput`
  - `user_id`
  - `segments`：`new_user`、`active`、`price_sensitive`、`high_value`、`churn_risk`
  - `preferred_categories`
  - `price_range`
  - `recent_interests`
  - `confidence`
  - `profile_source`
  - `data_source`
  - `explanation`、`warnings`
- 依赖：`UserBehaviorRepository` + `LLMProvider`。
- 规则：
  - 新用户：账号年龄小于 7 天；或没有账号年龄且交互信号很少。
  - 活跃：7 天内活跃且交互数至少 3。
  - 价格敏感：平均订单金额不高于 100。
  - 高价值：平均订单金额不低于 500。
  - 流失风险：30 天以上不活跃、非新用户且存在历史交互。
- 结构化字段完全由规则推导。LLM 只生成解释，不参与事实判断。
- 运行期合并策略：输入中显式提供的非空行为字段覆盖 Repository 中的对应字段。
- Mock LLM 失败时仍返回成功画像，`profile_source=rule_based`，并写入
  `warnings=["mock_llm_unavailable"]`。

### 3.2 CatalogAgent

- 稳定名称：`catalog_agent`
- 输入：`CatalogInput`
  - `query`、`category`、`min_price`、`max_price`、`limit`
- 输出：`CatalogOutput`
  - `products`、`matched_count`、`query`、`filters`、`source`
- 依赖：`CatalogRepository` + `LLMProvider`。
- 关键词搜索不区分大小写；多个关键词 token 采用 AND 语义。
- 分类过滤不区分大小写；价格边界包含端点。
- `matched_count` 是应用 `limit` 之前的匹配总数。
- `source=in_memory_demo`。
- 不实现 embedding、向量检索、RAG 或协同过滤。

### 3.3 RecommendationAgent

- 稳定名称：`recommendation_agent`
- 输入：`RecommendationInput`
  - `user_profile`
  - `candidate_products`
  - `num_items`
- 输出：`RecommendationOutput`
  - `products`
  - `ranking_reasons`（按 `product_id` 组织）
  - `strategy=rule_based_demo`
  - `filtered_count`
  - `confidence`
- 依赖：`LLMProvider`（统一依赖契约；排序不读取 LLM 文本）。
- 排序规则：
  - 类目匹配 `category_match`：+30。
  - 价格区间 `within_price_range`：+15。
  - 有库存 `in_stock`：+5。
  - 标签与兴趣匹配 `tag_match`：+20。
  - 每类目最多返回 2 个商品；未出现过的类别获得 `diversity_bonus`。
  - 重复 `product_id` 和 `stock <= 0` 的候选在排序前被过滤。
  - 按分数降序、`product_id` 升序进行稳定排序。
- 不调用其他 Agent，不使用随机数，不访问网络。
- 候选为空或无有效候选时返回空 products、空 reasons、`confidence=0.0`。

### 3.4 InventoryAgent

- 稳定名称：`inventory_agent`
- 输入：`InventoryInput`
  - `products`
  - `low_stock_threshold`
- 输出：`InventoryOutput`
  - `available_products`
  - `unavailable_products`
  - `low_stock_alerts`
  - `purchase_limits`
  - `unavailable_reasons`
  - `source`
- 依赖：`InventoryRepository` + `LLMProvider`。
- 规则：
  - 库存 `<= 0`：不可售。
  - 库存记录缺失：不可售，原因 `inventory_record_missing`，不默认为充足。
  - `1 <= stock <= threshold`：低库存，生成预警，限购 `min(stock, 2)`。
  - 正常库存不产生限购记录。
- 通过 `model_copy(deep=True)` 写入解析后的库存，不修改调用方商品对象。
- Repository 抛出异常或返回非法库存时，BaseAgent 返回结构化失败结果。

### 3.5 MarketingAgent

- 稳定名称：`marketing_agent`
- 输入：`MarketingInput`
  - `user_profile`
  - `products`
  - `style`（可选覆盖）
- 输出：`MarketingOutput`
  - `copies`：每个元素包含 `product_id`、`copy`、`style`、
    `compliance_passed`、`warnings`、`provider`
  - `style`
- 依赖：`LLMProvider`。
- 风格推导：
  - `churn_risk` → `recall`
  - `new_user` → `welcome`
  - `high_value` → `premium`
  - `price_sensitive` → `value`
  - `active` → `active`
- 商品事实只来自模板和真实 `Product` 字段。
- LLM 只允许从安全开场语白名单中选择（`为你精选`、`值得关注`、`今日推荐`、
  `不妨看看`）；其他 LLM 文本一律忽略，防止 Mock 输出被当作商品事实。
- Mock 失败时自动回退到规则模板，`provider=rule_based`。
- 风险词检查：`国家级`、`第一`、`最好`、`绝对`、`100%`。
- 本阶段只做基础敏感词检查，**不声称完成完整广告法审查**。

## 4. 数据访问协议与适配器

协议位于 `domain/ports.py`：

```python
class CatalogRepository(Protocol):
    source: DataSource
    def search(...) -> list[Product]: ...

class InventoryRepository(Protocol):
    source: DataSource
    def get_stock(product_id: str) -> int | None: ...

class UserBehaviorRepository(Protocol):
    source: DataSource
    def get_behavior(user_id: str) -> UserBehaviorRecord | None: ...
```

适配器位于 `infrastructure/data/`：

- `InMemoryCatalogRepository`
- `InMemoryInventoryRepository`
- `InMemoryUserBehaviorRepository`

设计约束：

- Agent 只依赖 Protocol，不依赖具体内存实现。
- 所有演示数据集中在 `demo_data.py`。
- 数据固定、可重复，不使用随机值。
- 适配器持有内部副本，读取时返回深拷贝，避免调用方污染数据源。
- `source=in_memory_demo` 明确标记演示来源。
- 默认数据不是真实商品、库存或客户数据。

## 5. Service 层

| Service | 调用的 Agent | 构造依赖 |
| --- | --- | --- |
| `ProfileService` | `UserProfileAgent` | UserBehaviorRepository + LLMProvider |
| `CatalogService` | `CatalogAgent` | CatalogRepository + LLMProvider |
| `ProductRecommendationService` | `RecommendationAgent` | LLMProvider |
| `InventoryService` | `InventoryAgent` | InventoryRepository + LLMProvider |
| `MarketingService` | `MarketingAgent` | LLMProvider |

Service 的职责仅限：

1. 接收已经通过 Pydantic 校验的输入。
2. 通过构造函数注入依赖并创建/持有一个 Agent。
3. 调用单个 Agent 的 `run(request=...)`。
4. 将失败 `AgentResult` 转换为 `AgentExecutionError`。
5. 用专用输出模型校验 `AgentResult.data`，返回结构化模型。

Service 不进行跨 Agent 编排，也不会自动调用 Supervisor。

### Agent 依赖注入说明

所有 Agent 的外部依赖都通过构造函数注入，禁止在 Agent 内部创建全局数据库、
HTTP 客户端或另一种 Agent。Profile/Catalog/Inventory 需要数据访问，因此注入对应
Repository；Recommendation 和 Marketing 的候选商品/商品列表由调用方通过输入提供，
因此不额外注入隐藏的数据仓库。五个 Agent 都接收 LLMProvider，以满足统一依赖契约；
Catalog、Inventory、Recommendation 的核心规则明确不依赖 LLM 输出。

## 6. 异常处理策略

- 输入错误：Pydantic `ValidationError`，在 Agent 执行前失败。
- 依赖或规则执行中的普通异常：`BaseAgent.run()` 捕获并返回失败 `AgentResult`。
- Service 检查 `AgentResult.success`：
  - 失败时抛出 `AgentExecutionError`，保留 `agent_error` 详情。
  - Agent 返回的数据不符合专用输出模型时，抛出 `AgentExecutionError`。
- 不静默忽略异常，不伪造成功结果。
- 本次阶段二的 Agent 不直接依赖 FastAPI，也不直接返回 HTTP 错误。

## 7. Mock 与演示数据边界

### Mock LLM

- 仅 `MockLLMProvider`，无网络、无 API Key。
- UserProfileAgent 的 LLM 失败会降级到规则画像。
- MarketingAgent 的 LLM 失败会降级到规则文案。
- MarketingAgent 不接受任意 LLM 文本作为商品描述，只接受安全开场语白名单。

### 内存演示数据

- 商品：10 个固定的演示商品。
- 库存：独立于 `Product.stock` 的固定库存映射。
- 用户行为：4 个演示用户记录。
- 全部位于 `infrastructure/data/demo_data.py`，不是真实业务数据。

## 8. API 边界

阶段一 API 不修改：

- `GET /health` 保持健康检查。
- `POST /api/v1/recommend` 仍返回 `status=skeleton`、空 products、DemoAgent 结果。
- 阶段二 Agent 已经可以通过 Service 独立调用，但本阶段不新增编排 API。
- 阶段一原有 API 测试必须继续通过。

## 9. 测试策略

- 每个 Agent 有独立的单元测试文件。
- 三个内存适配器分别有过滤、拷贝隔离、来源标记或非法数据测试。
- `test_agent_contracts.py` 校验五个 Agent 都继承 BaseAgent、名称稳定、输入输出为
  Pydantic 模型、Marketing JSON 字段契约正确。
- `test_phase2_agent_flow.py` 只验证服务可以在外部传入数据的情况下独立运行，
  不使用 Supervisor、网络、API Key、Redis 或数据库。
- 运行：`pytest -q`。

## 10. 后续扩展点

### 接入真实数据库

用实现同一 Protocol 的 PostgreSQL/Redis 适配器替换内存适配器即可，Agent 不需要
知道存储实现。数据模型中的 `source` 字段应从 `in_memory_demo` 扩展为真实来源枚举。

### 接入 RAG / 向量检索

在 `CatalogRepository` 后增加检索适配器，或在未来新增 `RetrievalRepository` 端口。
当前 CatalogAgent 的规则关键词搜索不应被描述成 RAG。

### 接入 Supervisor / LangGraph

后续阶段可以将 Service 或 Agent 作为图节点：

- `UserProfileAgent` 生成画像节点输出。
- `CatalogAgent` 提供候选商品节点。
- `RecommendationAgent` 做排序节点。
- `InventoryAgent` 做库存约束节点。
- `MarketingAgent` 做文案节点。
- Supervisor 负责节点间的状态路由和失败降级。

当前阶段明确**未实现**这些节点、边、状态传递和并行调度。未来接入时不要绕过 Service
直接共享全局状态，也不要让 Agent 相互创建实例。

### 接入真实 LLM

替换 `LLMProvider` 工厂实现即可。真实 Provider 必须继续遵守：

- 不把 LLM 自由文本直接作为结构化画像事实。
- 不把 LLM 输出直接作为推荐排序结果。
- 营销文案需要更完整的事实校验与合规审查。

## 11. 已知限制与技术债

1. `MockLLMProvider` 返回固定文本，无法验证真实模型质量。
2. MarketingAgent 的敏感词检查只是基础演示，不是完整广告法审查。
3. RecommendationAgent 的权重和推荐解释是阶段二演示规则，未经真实业务评估。
4. `filtered_count` 只统计排序前被去重或库存淘汰的候选，不包含类目多样性或
   `num_items` 截断造成的未返回商品。
5. 库存与商品数据没有一致性事务，真实接入时需要仓储层保证。
6. 当前没有数据库迁移、并发控制、缓存、限流或生产级监控。
