# 阶段四验收记录

> 验收日期：2026-11-27（Asia/Shanghai）
>
> 结论：阶段四核心能力已实现并通过离线测试。真实 Redis、PostgreSQL/MySQL 和外部
> 向量数据库没有在本机验证，本文明确列出这些边界。

## 1. 环境

| 组件 | 版本/状态 |
| --- | --- |
| Python | 3.12.0 |
| FastAPI | 0.138.0 |
| Pydantic | 2.13.4 |
| LangGraph | 1.2.9 |
| SQLAlchemy | 2.0.51 |
| Alembic | 1.18.5 |
| Redis Python 包 | 未安装 |
| Redis 服务 | 未运行/未验证 |
| PostgreSQL/MySQL | 未验证 |
| 外部向量数据库 | 未使用 |
| LLM | 仅 `MockLLMProvider` |

## 2. 实际执行结果

### 全量测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

实际输出：

```text
237 passed, 1 warning in 4.89s
```

唯一 warning 是第三方 FastAPI/Starlette TestClient 对 httpx 的弃用提示，不是项目
测试失败。

### Lint

```powershell
py -3.12 -m ruff check src tests migrations
```

实际结果：

```text
All checks passed!
```

### 迁移

```powershell
$env:DATABASE_URL = "sqlite:///<临时目录>/migrate.db"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

实际创建：

```text
alembic_version, inventory_records, product_embeddings,
products, user_behaviors, user_profiles, users
```

迁移也由 `tests/integration/test_alembic_migration.py` 自动测试。

## 3. 验收项对照

| 验收项 | 实现 | 证据 |
| --- | --- | --- |
| SQLAlchemy 2.x + SQLite | 是 | `infrastructure/database/` |
| PostgreSQL/MySQL 可配置 | URL 支持 | `DATABASE_URL` 校验 |
| Alembic 迁移 | 是 | `migrations/`、迁移测试 |
| 商品表/Repository | 是 | `products`、`DatabaseCatalogRepository` |
| 库存表/Repository | 是 | `inventory_records`、`DatabaseInventoryRepository` |
| 用户表/Repository | 是 | `users`、`DatabaseUserRepository` |
| 行为表/Repository | 是 | `user_behaviors`、`DatabaseUserBehaviorRepository` |
| 画像表/Repository | 是 | `user_profiles`、`DatabaseUserProfileRepository` |
| 种子数据幂等 | 是 | `seed_demo_database`、测试 |
| Redis 适配器 | 是 | `RedisMemoryStore` |
| InMemory 降级 | 是 | `InMemoryMemoryStore`、降级测试 |
| 画像缓存/TTL | 是 | Redis/InMemory、TTL 测试 |
| 确定性 Embedding | 是 | `DeterministicEmbeddingProvider` |
| 本地向量存储 | 是 | `InMemoryVectorStore`、`SQLiteVectorStore` |
| 向量索引及重建 | 是 | 启动时从商品表重建 |
| RAG 分数/来源 | 是 | `RetrievedCandidate`、`RetrievalResult` |
| RAG 过滤 | 是 | 上下架、类目、价格、库存 |
| RAG 失败回退 | 是 | 关键词检索 + warnings |
| 画像优先级 | 是 | 显式 > Redis/记忆 > 缓存 > DB 历史 > 持久画像 > 默认 |
| 画像持久化 | 是 | SQLite/内存 ProfileRepository |
| CatalogAgent 语义检索 | 是 | 注入 `RetrievalPort` |
| RecommendationAgent 最终排序 | 是 | 规则排序 + 有界语义辅助分 |
| InventoryAgent 真实库存 | 是 | 注入数据库库存 Repository |
| Supervisor/图拓扑保持 | 是 | 原 8 节点拓扑 |
| 状态来源字段 | 是 | `retrieval_sources`、`retrieval_scores`、`profile_source`、`memory_source`、`data_source` |
| 响应来源字段 | 是 | `retrieval_source`、`embedding_provider`、`memory_source` |
| 目录搜索 API | 是 | `POST /api/v1/catalog/search` |
| 行为 API | 是 | `POST /api/v1/users/{id}/behaviors` |
| 画像 API | 是 | `GET /api/v1/users/{id}/profile` |
| 检索 API | 是 | `POST /api/v1/retrieval/search` |
| 阶段一 skeleton 保留 | 是 | 全量回归 |
| 阶段二单 Agent 保留 | 是 | 全量回归 |
| 阶段三工作流保留 | 是 | 全量回归 |
| 无 HITL/评估平台/分布式部署 | 是 | 明确未实现 |

## 4. 阶段四新增测试覆盖

- `tests/unit/test_database_repositories.py`
  - schema 表集合、种子幂等。
  - 商品/库存查询与更新。
  - 行为事件写入/最近读取/聚合。
  - 画像 upsert、读取、失效。
- `tests/unit/test_cache_and_vector.py`
  - InMemory 行为、画像缓存、session、TTL。
  - Redis 假客户端：key 前缀、TTL、JSON 往返、关闭。
  - Redis 操作失败抛出结构化 `ExternalServiceError`。
  - Redis 包缺失时显式回退 InMemory。
  - 确定性 Embedding 稳定性和 batch。
  - InMemory/SQLite 向量索引与检索。
- `tests/unit/test_retrieval_service.py`
  - 向量召回分数/来源。
  - 类目、价格、上下架、库存过滤。
  - 向量故障/Embedding 故障回退关键词。
- `tests/unit/test_profile_persistence.py`
  - 画像持久化与缓存命中。
  - 实时行为优先于历史/持久数据。
  - 显式输入优先于实时行为。
  - 重建服务后从数据库恢复画像。
  - 缓存与持久画像失效。
  - Redis 故障降级到数据库画像并返回警告。
- `tests/integration/test_phase4_api_real_database.py`
  - SQLite 真实应用的 health/catalog/retrieval/profile/behavior/workflow。
  - 默认离线应用仍可 RAG。
  - 阶段一 skeleton 未变。
- `tests/integration/test_phase4_workflow_state.py`
  - 工作流状态记录检索来源、分数、画像来源、数据来源。
- `tests/integration/test_alembic_migration.py`
  - 迁移可执行并创建完整表集合。
- `tests/regression/test_phase3_compatibility_after_phase4.py`
  - 不注入阶段四服务时，原阶段三 Supervisor 仍成功。
- 原有阶段一/二/三测试全部保留。

## 5. 外部服务与降级

### 默认测试

默认 `USE_REAL_ADAPTERS=false`、`REDIS_ENABLED=false`：

- 不创建 SQLite 文件。
- 不连接 Redis。
- 不连接外部向量库。
- 不访问网络。
- 使用 InMemory Repository、InMemoryMemoryStore、InMemoryVectorStore。

### 启用 SQLite

设置：

```env
USE_REAL_ADAPTERS=true
DATABASE_URL=sqlite:///./data/agentic_commerce.db
SEED_DEMO_DATA=true
```

应用会创建数据库、按配置写入演示数据、建立本地向量索引。

### 启用 Redis

设置 `REDIS_ENABLED=true` 并提供 `REDIS_URL`。行为、画像缓存和 session 会走 Redis。

已实现的故障处理：

- Redis Python 包缺失：应用记录警告，使用 `InMemoryMemoryStore`。
- Redis 初始化失败：记录警告，使用 `InMemoryMemoryStore`。
- 运行期 Redis 读取/写入失败：Profile 流程记录警告并降级到数据库；行为 API 返回
  结构化 `503`，不伪造成功。
- Redis 客户端关闭失败：记录警告，不影响响应。

**未验证**：真实 Redis 连接、真实 TTL 到期、Redis 重启恢复。Redis 适配器测试使用
假客户端；本机没有 Redis 服务和 Python 客户端。

### PostgreSQL/MySQL

配置层支持 `postgresql:`/`mysql:` URL，Repository 使用通用 SQLAlchemy。但本机
没有这两个服务，因此未做真实连接、事务、时区、迁移和性能验证。

## 6. 本轮实际失败与修复

1. Alembic 测试首次加入后，`test_workflow_observability` 找不到 `workflow_completed`。
   - 原因：Alembic `fileConfig` 默认 `disable_existing_loggers=True`，关闭了后续测试
     使用的应用 logger。
   - 修复：`fileConfig(..., disable_existing_loggers=False)`。
2. 早期测试检索服务时直接访问私有向量字段，测试可维护性差。
   - 修复：改为通过构造参数显式注入共享向量存储。
3. `MockLLMProvider` 测试导入路径使用错误模块名。
   - 修复：改为 `infrastructure.llm.mock_provider`。

最终全量测试 237 passed，无项目功能失败。

## 7. 明确未完成/未验证

- 真实 LLM；仍为 Mock。
- 真实 Redis 服务集成、连接池、集群、监控。
- 真实 PostgreSQL/MySQL 连接和迁移。
- 外部 Qdrant/Chroma 向量数据库；当前是进程内/SQLite 余弦检索。
- 语义 Embedding 模型；当前为确定性哈希向量。
- 生产规模向量索引（Python 全量余弦计算）。
- 异步数据库访问；Repository 当前同步。
- HITL、审批、可中断工作流。
- 完整 Agent 评估集、指标平台、Prometheus/OpenTelemetry。
- Docker Compose/容器镜像；本阶段未提供，直接本地运行。
- 鉴权、限流、多租户、分布式调度。
- 真实订单、支付、WMS、广告法审查。

## 8. 技术债与后续建议

1. 将数据库 Repository 迁移为异步 SQLAlchemy 或独立数据服务。
2. 商品规模增大时接入 Qdrant/Chroma/pgvector，并保留当前端口。
3. 增加真实 Redis 集成测试（Testcontainers 或 CI 服务）。
4. 对 PostgreSQL/MySQL 增加迁移、时区和并发测试。
5. 增加画像/检索质量评估集，而非只测结构正确性。
6. 评估 RAG 缓存、索引增量更新和失效策略。
7. 明确画像数据保留期、删除接口和隐私合规策略。
8. 为缓存/数据库降级增加可观测指标，而不只依赖日志和 warnings。

## 9. 最终声明

阶段四实现了可在本地离线验证的 SQLite 持久化、记忆优先级、画像持久化、确定性
Embedding/RAG、真实数据工作流和来源追踪。没有把内存适配器冒充数据库、没有把哈希
向量冒充语义模型、也没有把假 Redis 客户端测试冒充真实 Redis 验证。
