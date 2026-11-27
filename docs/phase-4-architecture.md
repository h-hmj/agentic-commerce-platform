# 阶段四：真实数据检索、RAG、用户画像持久化与记忆

## 1. 阶段边界

阶段四在保留阶段一到三所有行为的前提下，增加了真实可运行的数据适配器：

- SQLAlchemy 2.x + SQLite 本地默认数据库；支持通过 URL 换成 PostgreSQL/MySQL。
- 商品、库存、用户、行为事件、画像快照的数据库 Repository。
- Redis 短期记忆适配器，以及默认的 `InMemoryMemoryStore` 降级。
- 确定性本地 Embedding、SQLite/进程内本地向量索引、RAG 召回。
- 画像持久化、画像缓存、实时行为优先的数据源优先级。
- 工作流状态与最终响应中的数据来源、检索来源、Embedding 来源和记忆来源字段。
- 新增目录搜索、行为写入、画像读取和检索 API。

本阶段仍然**不是**：

- 真实 LLM 调用；仍然只使用 `MockLLMProvider`。
- 生产级分布式数据库、Redis 集群、向量数据库集群。
- Human-in-the-loop、完整 Agent 评估平台、Prometheus/OpenTelemetry 平台。
- 真实支付、订单、WMS、推荐模型训练。
- 对 Redis 真实服务的自动化测试。

## 2. 架构

```text
API routes
  ├── /api/v1/recommend (阶段一 skeleton，保持不变)
  ├── /api/v1/workflow/recommend
  ├── /api/v1/catalog/search
  ├── /api/v1/retrieval/search
  └── /api/v1/users/{id}/profile, /behaviors
        │
        ▼
Services
  ├── WorkflowService / ProfileService / CatalogService
  ├── RetrievalService / EmbeddingService / MemoryService
        │
        ▼
Agents + LangGraph Supervisor
  ├── UserProfileAgent
  ├── CatalogAgent
  ├── RecommendationAgent
  ├── InventoryAgent
  └── MarketingAgent
        │
        ▼
Domain ports
  ├── CatalogRepository / InventoryRepository
  ├── UserBehaviorRepository / UserProfileRepository / UserRepository
  ├── MemoryStore
  └── EmbeddingProvider / VectorStore / RetrievalPort
        │
        ▼
Infrastructure
  ├── SQLAlchemy DatabaseManager + repositories
  ├── InMemory adapters
  ├── RedisMemoryStore + InMemoryMemoryStore
  └── DeterministicEmbeddingProvider + local vector stores
```

依赖方向仍然是 `api → services/orchestration → agents → domain ports → infrastructure`。
Agent 不直接创建数据库 Session、Redis 客户端或向量数据库客户端。

## 3. 配置与运行模式

`Settings` 新增的关键字段：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/agentic_commerce.db` | SQLAlchemy URL |
| `USE_REAL_ADAPTERS` | `false` | `true` 时使用 SQLite/数据库适配器 |
| `SEED_DEMO_DATA` | `true` | 新库写入明确标记的演示数据 |
| `REDIS_ENABLED` | `false` | 关闭时使用 InMemoryMemoryStore |
| `REDIS_URL` | `redis://localhost:6379/0` | `SecretStr`，可含密码 |
| `REDIS_KEY_PREFIX` | `agentic-commerce` | 所有 Redis key 的前缀 |
| `EMBEDDING_PROVIDER` | `deterministic` | 仅本地确定性实现 |
| `EMBEDDING_MODEL` | `deterministic-hash-v1` | 稳定模型标识 |
| `EMBEDDING_DIMENSIONS` | `64` | 确定性向量维度 |
| `RETRIEVAL_TOP_K` | `8` | 向量召回上限 |
| `RETRIEVAL_SCORE_THRESHOLD` | `0.05` | 最低余弦相似度 |

默认 `USE_REAL_ADAPTERS=false`，保证 `pytest -q` 不写数据库、不依赖 Redis 或网络。
需要真实 SQLite 持久化时在 `.env` 设置 `USE_REAL_ADAPTERS=true`。

SQLite 数据库路径父目录由 `DatabaseManager` 自动创建。生产数据库连接串通过
`DATABASE_URL` 提供，不把密码写入代码或日志。

## 4. 数据库设计

| 表 | 职责 |
| --- | --- |
| `products` | 商品事实：名称、类目、价格、品牌、描述、标签、上下架 |
| `inventory_records` | 库存事实：可用库存、预留库存、更新时间 |
| `users` | 用户身份与注册时间 |
| `user_behaviors` | 追加式行为事件：view/click/purchase、商品、类目、金额、时间 |
| `user_profiles` | 画像快照：分群、偏好类目、价格区间、兴趣、来源、警告 |
| `product_embeddings` | 本地向量索引：商品、集合、文本、向量、模型 |
| `alembic_version` | 迁移版本 |

关键约束：

- 商品、库存商品、用户、画像用户、向量商品都有唯一约束。
- 库存通过 `product_id` 外键关联商品。
- 行为与画像通过 `user_id` 外键关联用户。
- 金额使用 `Numeric(12,2)`；时间使用带时区的 `DateTime`。
- 商品上下架由 `is_active` 控制，RAG 不返回下架商品。

**库存唯一来源**：`DatabaseInventoryRepository` 直接读取 `inventory_records`；
`DatabaseCatalogRepository` 只把库存表中的 `stock` 投影到商品读取结果。库存缺失时
Catalog 投影为 0，InventoryAgent 仍会把缺失记录视为不可售，不默认有货。

## 5. Repository 与数据来源

新增/扩展的领域端口：

- `CatalogRepository`：`search`、`get_by_ids`。
- `InventoryRepository`：`get_stock`、`get_stock_levels`、`update_stock`。
- `UserBehaviorRepository`：聚合读取、最近事件读取、事件写入。
- `UserProfileRepository`：读取/保存/失效画像。
- `UserRepository`：确保用户存在。
- `MemoryStore`：行为、画像缓存、会话上下文。
- `EmbeddingProvider`、`VectorStore`、`RetrievalPort`。

所有返回值携带显式来源：

- `DataSource.DATABASE`
- `DataSource.REDIS`
- `DataSource.IN_MEMORY`
- `DataSource.IN_MEMORY_DEMO`
- `DataSource.HYBRID`
- `DataSource.DEFAULT`

不允许把内存数据标记成数据库数据，也不允许把降级结果伪装成真实检索成功。

## 6. 用户画像与记忆

### 6.1 数据源优先级

`UserProfileAgent` 按以下顺序选择事实来源：

1. 请求中显式提供的画像行为；
2. Redis（或 InMemory）实时行为事件；
3. 可用画像缓存；
4. 数据库历史行为聚合；
5. 数据库已保存画像；
6. 默认画像。

说明：缓存位于“实时行为之后、历史重建之前”，这样没有新行为时可以直接复用画像；
有新实时行为时缓存被绕过/失效。画像缓存失效后会从数据库画像或历史行为恢复。

### 6.2 规则画像与 LLM 边界

结构化事实（分群、偏好类目、价格区间、兴趣、置信度）始终由规则生成。
`MockLLMProvider` 只能提供解释文本，不能提供画像事实。LLM 失败只产生
`mock_llm_unavailable` 警告，不改变规则事实。

画像保存失败、缓存写入失败、Redis 读取失败都记录结构化警告，画像流程继续使用
可用数据，不会因为缓存故障而伪造成功。

### 6.3 实时行为

`POST /api/v1/users/{user_id}/behaviors`：

1. 先写数据库历史（持久事实）；
2. 再写短期记忆；
3. 短时缓存故障会以 `ExternalServiceError` 返回，不会声称 Redis 写入成功；
4. 失效该用户画像缓存。

`GET /api/v1/users/{user_id}/profile` 通过 `ProfileService`/`UserProfileAgent`
构建或读取画像，并返回 `data_source`、`memory_source`、`profile_persisted`。

### 6.4 Redis key 与 TTL

`RedisMemoryStore` 的 key 示例（均带 `REDIS_KEY_PREFIX` 前缀）：

- `agentic-commerce:behavior:{user_id}:all`
- `agentic-commerce:behavior:{user_id}:{behavior_type}`
- `agentic-commerce:profile:{user_id}`
- `agentic-commerce:session:{session_id}`

行为列表裁剪到最近 200 条；行为、画像、会话均设置有限 TTL。库不存在或客户端
初始化失败时，应用记录警告并使用 `InMemoryMemoryStore`。真实 Redis 服务未在本机
验证，见验收文档。

## 7. RAG 与本地向量检索

### 7.1 Embedding

`DeterministicEmbeddingProvider` 是基于 SHA-256 token 哈希的确定性向量。它用于本地
联调和测试，**不是**语义神经网络模型，也不应被描述为生产 Embedding。

### 7.2 向量存储

- 离线/测试：`InMemoryVectorStore`，进程内余弦相似度。
- 使用真实 SQLite 适配器：`SQLiteVectorStore`，向量写入 `product_embeddings`。
- 相似度在 Python 中计算，适合当前小规模数据；不是生产向量数据库的替代。

### 7.3 检索流水线

```text
query
  → DeterministicEmbeddingProvider
  → VectorStore.search(top_k, threshold)
  → active/category/price/inventory 过滤
  → RetrievalResult(candidates, score, source, warnings)
  → CatalogAgent
  → RecommendationAgent 最终规则排序
```

- 相似度只作为召回和辅助 tie-breaker，不直接决定最终推荐顺序。
- `RecommendationAgent` 仍是最终规则排序器：类目、价格、库存、标签，加上一个
  有界的 `semantic_match` 辅助分。
- `InventoryAgent` 仍是最终库存权威。
- Embedding 或向量检索失败时，`RetrievalService` 回退到结构化关键词检索，并在
  `warnings` 中返回 `embedding_failed` 或 `vector_retrieval_failed`。
- 候选结果带 `score`、`source`、`retrieval_query`、`matched_fields`、`embedding_model`。

## 8. 工作流集成

阶段三图拓扑保持不变：

```text
initialize_request
  ├── user_profile ──┐
  └── catalog ───────┴──> recommendation
                              → inventory
                              → inventory_filter
                              → marketing
                              → aggregate
```

新增状态字段：

- `retrieval_sources: dict[str, str]`
- `retrieval_scores: dict[str, float]`
- `profile_source: str | None`
- `memory_source: str | None`
- `data_source: str`

Catalog 节点把 RAG 来源和分数写回状态；Recommendation 节点只把它们作为可选语义
辅助分；Profile 节点记录画像来源和记忆来源。

最终 `WorkflowRecommendationResponse` 新增：

- `retrieval_source`
- `embedding_provider`
- `memory_source`
- 原有 `data_source`

## 9. 新增 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/catalog/search` | 结构化/可选 RAG 商品搜索 |
| `POST` | `/api/v1/retrieval/search` | 直接返回 RAG 候选、分数、来源 |
| `GET` | `/api/v1/users/{user_id}/profile` | 读取/构建持久画像 |
| `POST` | `/api/v1/users/{user_id}/behaviors` | 写入行为事件 |
| `POST` | `/api/v1/workflow/recommend` | 保留阶段三工作流 |
| `POST` | `/api/v1/recommend` | 保留阶段一 skeleton |

## 10. 迁移

初始迁移：

```bash
python -m alembic upgrade head
```

运行时会读取 `DATABASE_URL` 环境变量，否则使用 `alembic.ini` 中的 SQLite 默认值。
应用启动时也会调用 `create_all()` 作为本地开发兜底；生产环境应使用 Alembic。

## 11. 测试策略

阶段四测试全部离线：

- SQLite 临时数据库 Repository/种子幂等/画像持久化测试。
- 确定性 Embedding、进程内向量、SQLite 向量存储测试。
- RAG 成功、过滤、向量故障回退、Embedding 故障回退测试。
- InMemory 记忆、缓存 TTL、会话、Redis 适配器假客户端、Redis 故障降级测试。
- 画像优先级、缓存、数据库恢复测试。
- 真实 SQLite API 端到端测试、工作流来源字段测试。
- Alembic 迁移测试。
- 阶段一/二/三兼容性回归测试。

未测试真实 Redis 服务、真实 PostgreSQL/MySQL、外部 Qdrant/Chroma 服务。

## 12. 已知技术债与边界

- SQLAlchemy Repository 目前是同步实现，在异步 Agent 调用中直接执行；SQLite 本地
  规模可接受，生产应改为异步 SQLAlchemy/连接池或独立数据服务。
- 向量相似度在 Python 中计算；商品规模变大后需要真正的向量索引。
- 确定性 Embedding 不是语义模型，检索质量只适合联调和演示。
- Redis 没有真实服务集成测试；Redis 适配器通过假客户端验证键前缀、TTL 和错误传播。
- 没有 HITL、评估平台、分布式追踪平台、Checkpoint 持久化。
- Docker Compose 未提供；本地直接运行 SQLite 和 InMemory/RAG 即可。
- 种子数据是演示数据，不能当作生产数据。
