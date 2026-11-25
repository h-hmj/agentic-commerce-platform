# 阶段三架构说明：Supervisor、多 Agent 协作与 LangGraph

## 1. 范围与边界

阶段三在阶段二的五个专业 Agent 之上，实现了真正可执行的多 Agent 协作流程：

```text
用户请求
→ FastAPI WorkflowService
→ SupervisorOrchestrator
→ LangGraph StateGraph
→ 用户画像 + 商品目录并行
→ 推荐排序
→ 库存决策
→ 库存过滤
→ 营销文案
→ 聚合响应
```

本阶段使用 LangGraph **1.2.9**（依赖声明 `langgraph>=1.2,<2.0`）构建并编译真实的
`StateGraph`。工作流通过异步节点执行，测试直接调用编译后的图。

明确不包含：

- Checkpoint 持久化、多轮会话记忆、HITL。
- 真实数据库、Redis、向量数据库、消息队列、Prometheus。
- Embedding、RAG、协同过滤、真实 LLM API。
- 真实订单、支付、WMS 或生产部署。
- 完整广告法审查或推荐质量评估。

阶段一 `/api/v1/recommend` skeleton 与阶段二单 Agent Service 均保持兼容。新增阶段三接口：

```text
POST /api/v1/workflow/recommend
```

## 2. 整体架构

```text
POST /api/v1/workflow/recommend
            │
            ▼
      WorkflowService
            │ 只调用 Supervisor
            ▼
  SupervisorOrchestrator
    │  注入五个 Agent、Repository bundle、LLMProvider、Settings、logger
    │  创建初始 state、执行编译图、转换最终响应
    ▼
  LangGraph StateGraph
    initialize_request
          ├── user_profile ──┐
          └── catalog ───────┴──> recommendation
                                  │
                                  ├──> inventory -> inventory_filter
                                  │        │
                                  │        └──> marketing
                                  └──────────────> aggregate
                                                       │
                                                      END
            │
            ▼
  WorkflowRecommendationResponse
```

阶段三的分层职责：

| 层 | 职责 |
| --- | --- |
| API route | 请求校验、request_id、调用 WorkflowService |
| WorkflowService | 单入口委托 Supervisor，不编排节点 |
| Supervisor | 依赖组装、图执行、异常兜底、状态转响应 |
| LangGraph nodes | 显式读取/写入状态，调用单个 Agent，路由与聚合 |
| Professional Agents | 画像、检索、排序、库存、营销业务规则 |
| Repositories | 只读内存数据，未来可替换 |
| MockLLMProvider | 离线解释/安全开场语，无网络 |

## 3. Supervisor 设计

`SupervisorOrchestrator` 位于
`src/agentic_commerce_platform/orchestration/supervisor.py`。

通过构造函数显式接收：

- `UserProfileAgent`
- `CatalogAgent`
- `RecommendationAgent`
- `InventoryAgent`
- `MarketingAgent`
- `WorkflowRepositories`：user behavior、catalog、inventory Repository
- `LLMProvider`
- `Settings`
- 可选 `logger`

Supervisor 的职责：

1. 创建带 request ID 的初始工作流状态。
2. 用五个注入 Agent 构建 `WorkflowNodes`，再构建并编译 LangGraph。
3. 在 request 日志上下文中执行 `graph.astream(..., stream_mode="values")`，逐步保留
   完整状态快照。
4. 捕获图级未知异常，用最后成功快照恢复并保留
   `agent_results`/`errors`/`warnings`，再生成安全失败状态。
5. 将最终状态转换为 `WorkflowRecommendationResponse`。
6. 保证最终 products 与 marketing copies 一致性。

Supervisor **不**实现画像、检索、排序、库存或文案规则。Agent 由应用工厂显式创建后
注入，Supervisor 不创建隐藏的全局 Agent。

## 4. 状态模型

`RecommendationWorkflowState` 位于
`src/agentic_commerce_platform/orchestration/state.py`，是 `TypedDict(total=False)`。

### 请求字段

- `request_id`
- `user_id`
- `scene`
- `num_items`
- `context`

### Agent 输入与中间结果

- `user_profile_input`、`user_profile`
- `catalog_input`、`candidate_products`
- `recommendation_input`、`ranked_products`
- `inventory_input`、`available_products`、`unavailable_products`、
  `inventory_alerts`
- `marketing_input`、`marketing_copies`

### 结果与可观测性

- `agent_results`：按 agent name 保存完整 `AgentResult`
- `errors`、`warnings`：稳定错误/警告代码
- `current_node`
- `workflow_status`：`running`、`success`、`partial_success`、`failed`
- `failed_stage`：用于路由和故障定位
- `started_at`、`completed_at`
- `started_at_monotonic`：内部耗时计算
- `total_latency_ms`
- `final_product_count`

### 合并规则

用户画像与商品目录节点并行执行，因此以下字段使用 `Annotated` reducer：

| 字段 | reducer | 原因 |
| --- | --- | --- |
| `agent_results` | `merge_agent_results` | profile 与 catalog 结果都保留 |
| `errors` | `merge_unique_strings` | 两个分支错误按顺序去重合并 |
| `warnings` | `merge_unique_strings` | 两个分支 warning 按顺序去重合并 |

其他字段均只有一个写入者：

- profile 写 `user_profile`。
- catalog 写 `candidate_products`。
- recommendation 写 `ranked_products`。
- inventory 写库存结果。
- filter 写最终可用商品顺序。
- marketing 写文案。
- aggregate 写最终状态和耗时。

`current_node` 由顺序节点（initialize/recommendation/inventory/filter/marketing/
aggregate）更新；profile 与 catalog 并行节点不写这个共享字段，而是在各自日志的
`current_node` extra 中记录节点名，避免并行写入竞争。最终状态的 `current_node` 为
`aggregate`。

状态不包含 API Key、Prompt 或完整用户画像敏感数据。日志不会输出完整 context。

## 5. LangGraph 节点

| 节点 | 职责 |
| --- | --- |
| `initialize_request` | 确认/生成 request_id，初始化时间、状态、错误、结果集合 |
| `user_profile` | 构造 `UserProfileInput`，调用 profile Agent，失败时使用显式默认画像 |
| `catalog` | 从 context 构造查询，调用 catalog Agent，保存候选商品 |
| `recommendation` | 等待 profile/catalog 汇聚，构造 `RecommendationInput`，调用排序 Agent |
| `inventory` | 用 ranked products 调用库存 Agent，失败时清空可售结果 |
| `inventory_filter` | 按 ranked 顺序保留 inventory approved products |
| `marketing` | 只把最终可售商品传给 marketing Agent，保存文案 |
| `aggregate` | 计算总耗时、最终状态、最终商品数 |

节点通过 `agent.run(request=...)` 调用 Agent，并验证 `AgentResult.success` 和专用
Pydantic 输出模型。节点不会创建 Agent，也不会直接调用其他 Agent。

## 6. 拓扑与并行

```text
START
  │
initialize_request
  ├───────────────┐
  ▼               ▼
user_profile     catalog       ← 同一 LangGraph superstep，并行
  └───────┬───────┘
          ▼
   recommendation
          │
   ┌──────┴─────────┐
   ▼                ▼
inventory        aggregate      ← 失败/空结果时条件跳过
   │
inventory_filter
   │
   ├───────────────┐
   ▼               ▼
marketing        aggregate      ← 库存失败时条件跳过营销
   │
   ▼
aggregate
   │
  END
```

实现方式：

- `initialize_request` 有两条静态出边到 `user_profile` 和 `catalog`，二者在同一
  LangGraph 并发 superstep 中执行。
- 两个分支都连到 `recommendation`，LangGraph 会等待二者完成后才执行推荐节点。
- 不使用 `asyncio.gather` 手工并联；并行由 LangGraph 图调度完成。
- `agent_results`、`errors`、`warnings` 使用 reducer，保证并行结果不会互相覆盖。
- 并行测试用两个带延迟的注入 Agent 验证实际重叠（`max_active >= 2`），不是只看代码
  中的边。

## 7. 成功流程

1. init 确认 request_id，设置 running。
2. profile 与 catalog 并行。
3. recommendation 接收 profile 和候选商品。
4. inventory 检查 ranked products。
5. inventory_filter 按 ranked 顺序保留可售商品。
6. marketing 只接收过滤后的商品。
7. aggregate：
   - 计算 `total_latency_ms`。
   - final products 非空、无 errors/warnings → `success`。
8. Supervisor 转换响应并附加 demo/mock 说明。

最终 `products` 是推荐排序后经库存过滤的顺序，缺货商品不会出现。
`marketing_copies` 的 product_id 必须属于最终 products。

## 8. Agent 失败与降级

| 失败 | 处理 | 结果 |
| --- | --- | --- |
| UserProfileAgent | 显式默认画像，记录失败 AgentResult/error/warning | 推荐可继续，通常 partial_success |
| CatalogAgent | 候选为空，写 error，跳过推荐 | failed，无虚假商品 |
| RecommendationAgent | ranked 为空，写 error，跳过库存 | failed，不把原始候选当结果 |
| InventoryAgent | 可售列表为空，写 error，跳过营销 | failed，不假设库存充足 |
| MarketingAgent | 保留已完成商品，文案为空，写 error | partial_success |
| Agent 输出模型校验失败 | 记录 `*_output_invalid`，不信任 data | 按对应 Agent 失败策略 |
| 图级未知异常 | Supervisor 通过 `astream` 的最后成功快照保留 `agent_results`/`errors`/`warnings`，追加 `workflow_execution_failed` | 无最终商品为 failed；已有商品则 partial_success；日志保留堆栈 |

空候选集与失败不同：

- catalog 成功但为空 → warning，最终 `partial_success`，products 为空。
- 全部候选缺货 → 推荐为空 → `partial_success`，products 为空，并写 warning。
- 有 agent error 且无最终商品 → `failed`。

## 9. 最终响应

模型：`WorkflowRecommendationResponse`，位于
`src/agentic_commerce_platform/orchestration/models.py`。

包含：

- `request_id`、`user_id`
- `status`、`workflow_status`
- `products`
- `marketing_copies`
- `unavailable_products`
- `inventory_alerts`
- `agent_results`
- `errors`、`warnings`
- `total_latency_ms`
- `data_source=in_memory_demo`
- `llm_provider=mock`
- `messages`（明确 demo 边界）

响应校验：

- products 不重复。
- 可售和不可售 product_id 不相交。
- marketing copy 只能引用最终 products。

## 10. API 兼容与演示边界

保留：

- `GET /health`
- `POST /api/v1/recommend`：阶段一 skeleton，行为未变。

新增：

- `POST /api/v1/workflow/recommend`：调用阶段三 Supervisor 工作流，返回真实工作流
  结构，但数据仍是 phase-2 in-memory demo data，LLM 仍是 Mock。

路由层只调用 `WorkflowService`，不调用任何专业 Agent。

## 11. 可观测性

日志至少包含：

- request_id
- current_node
- workflow_status
- agent_name
- duration_ms
- final_product_count
- error_code（有错误时）

各节点记录开始/完成事件和耗时；Agent 由 BaseAgent 记录自己的成功/失败。日志不输出
API Key、Prompt、完整用户行为或请求上下文。

## 12. 测试策略

- 状态与 reducer 测试。
- 每个 LangGraph 节点的独立测试。
- 条件路由测试。
- Supervisor 依赖注入与完整执行测试。
- 编译图结构、成功、空结果、全缺货测试。
- 并行重叠与并行失败保留测试。
- 每种 Agent 失败、输出校验失败、未知图异常测试。
- API 工作流成功、422、部分失败、无网络测试。
- 阶段一/二回归测试。

运行：

```bash
python -m pytest -q
```

## 13. 后续扩展

### Checkpoint

在 `build_recommendation_graph()` 编译时注入 LangGraph checkpointer，以
`thread_id=request_id` 保存状态。当前代码没有 checkpointer，禁止声称已支持持久化。

### Redis / 数据库

- 替换三个 Repository 的内存实现。
- 用 Redis 做会话或分布式 checkpoint 存储。
- 在 agent_results 和 state 中加入持久化版本/来源字段。

### RAG

在 `CatalogRepository` 后增加 retrieval 端口和向量检索适配器。当前 CatalogAgent 只是
关键词过滤，不是 RAG。

### 真实 LLM

替换 `LLMProvider` 工厂即可。必须保留：

- 画像事实规则化。
- 排序不由 LLM 决定。
- 营销文案事实校验和合规审查。
- 失败安全降级。

### 可观测性

接入 OpenTelemetry/Prometheus/结构化事件表；当前只有标准日志。不要记录敏感内容。
