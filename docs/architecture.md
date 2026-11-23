# 阶段一架构说明

> **历史文档说明**：本文描述阶段一的工程骨架。阶段二已经新增五个可独立运行的
> 专业 Agent、内存数据适配器和新 Service，但尚未接入 Supervisor 或 LangGraph。
> 阶段二实现请阅读 [phase-2-architecture.md](phase-2-architecture.md)。

## 1. 范围

本文描述 `agentic-commerce-platform` 阶段一的工程骨架。阶段一的目标不是实现
推荐业务，而是建立可运行、可测试、可扩展的分层基础，使后续 Agent、LangGraph、
RAG、记忆和可观测性能力可以在稳定边界上逐步接入。

### 阶段一包含

- FastAPI 最小服务与健康检查。
- 推荐接口骨架、服务层和演示 Agent。
- Pydantic v2 领域契约。
- 配置、异常、日志、LLM Provider 抽象。
- 后续 LangGraph 状态类型。
- 离线测试。

### 阶段一不包含

- 真实商品数据、检索、排序和推荐。
- 真实 LLM 调用。
- Supervisor、图节点、并行 Agent 协作。
- 数据库、Redis、向量数据库、消息队列和监控系统。
- 用户画像、长期记忆和 Human-in-the-loop。

## 2. 分层结构

```text
HTTP Client
    │
    ▼
API 层（FastAPI routes / middleware / exception handlers）
    │  只做协议适配、依赖查找、request_id 和错误映射
    ▼
Service 层（RecommendationService）
    │  负责用例编排、计时、日志、异常转换
    ▼
Agent 层（BaseAgent / DemoAgent）
    │  负责生命周期、超时、重试扩展点、统一 AgentResult
    ▼
Infrastructure 层（LLMProvider / MockLLMProvider / logging）
    │
    ▼
Domain 层（models / enums / errors）
```

依赖方向总体为：API → Service → Agent/Infrastructure → Domain。Domain 不依赖
FastAPI、LLM 或具体存储实现。当前 `DemoAgent` 是阶段一唯一的具体 Agent，
并且只是链路演示。

## 3. 模块职责

| 模块 | 职责 |
| --- | --- |
| `settings.py` | 从环境变量/`.env` 加载并校验配置，保护 API Key |
| `domain/models.py` | 请求、商品、Agent 结果、响应、错误的 Pydantic 契约 |
| `domain/enums.py` | 推荐场景与响应状态枚举 |
| `domain/errors.py` | 项目级异常层级与稳定错误码 |
| `agents/base.py` | Agent 公共生命周期：计时、日志、超时、异常转结果、重试钩子 |
| `agents/demo.py` | 仅用于验证链路的 DemoAgent，不做业务推荐 |
| `services/recommendation_service.py` | 用例编排：request_id、调用 Agent、构造响应、异常处理 |
| `infrastructure/llm/base.py` | 与供应商无关的 `LLMProvider` Protocol |
| `infrastructure/llm/mock_provider.py` | 完全离线、确定性的 Mock Provider |
| `infrastructure/observability/logging.py` | 统一日志格式、request_id/agent_name 上下文 |
| `orchestration/state.py` | 为未来 LangGraph 预留的 TypedDict 状态 |
| `api/app.py` | FastAPI 工厂、依赖组装、路由注册 |
| `api/middleware.py` | request_id 解析、访问日志、`X-Request-ID` |
| `api/exception_handlers.py` | 异常到稳定 JSON 的集中映射 |
| `api/dependencies.py` | 从 `app.state` 获取单例配置与服务 |
| `api/routes/*` | 薄路由：校验、依赖注入、调用 Service |

## 4. 推荐请求时序

```text
Client
  │ POST /api/v1/recommend + X-Request-ID
  ▼
Request middleware
  │ 校验/生成 request_id，绑定日志上下文，开始计时
  ▼
FastAPI route
  │ Review Pydantic 校验，获取 RecommendationService
  ▼
RecommendationService
  │ 生成/沿用 request_id，记录开始日志
  │ 调用 DemoAgent.run(request=request)
  ▼
BaseAgent
  │ 计时、日志、asyncio.wait_for 超时
  ▼
DemoAgent
  │ 组装“阶段一链路检查”提示词
  ▼
MockLLMProvider
  │ 返回固定 Mock 文本，无网络
  ▼
BaseAgent
  │ 统一 AgentResult，补齐 agent_name 和 latency_ms
  ▼
RecommendationService
  │ 检查 success，构造 status=skeleton、products=[] 的响应
  ▼
Route → Middleware
  │ 添加 X-Request-ID，记录成功/失败与总耗时
  ▼
Client
```

## 5. 配置设计

`Settings` 继承 `pydantic_settings.BaseSettings`：

- 配置来源：`.env` 和同名环境变量（大小写不敏感）。
- 默认值适用于本地开发；API Key 默认为空。
- `app_env` 限制为 `development`、`test`、`production`。
- `log_level`、`log_format`、端口和 Provider 有显式校验。
- 生产环境禁止 `debug=true`。
- 阶段一仅接受 `llm_provider=mock`，防止配置了未实现的真实 Provider 却静默降级。
- API Key 使用 `SecretStr`，格式化 settings 对象不会泄露真实值。
- `get_settings()` 使用 `lru_cache`，保证进程级配置只加载一次。

配置错误会抛出 `ConfigurationError`，不会带病启动，也不会在 API 响应中回显配置值。

## 6. 领域契约

- `RecommendationContext` 使用显式字段而不是自由字典，拒绝未知字段。
- `RecommendationRequest.user_id` 非空，`scene` 默认 `home`，`num_items` 限制为 1–50。
- `Product` 的价格使用 `Decimal`，价格与库存均不允许为负数。
- `AgentResult` 要求失败时必须有 `error`，成功时不能携带 `error`。
- `RecommendationResponse` 明确 `status` 和 `total_latency_ms`。
- `ErrorResponse` 由 `request_id + error{code,message,details}` 组成，所有受控错误共用。
- 所有模型 `extra="forbid"`，避免未知字段悄悄进入系统。

## 7. 异常与错误映射

```text
EcommercePlatformError
├── ConfigurationError          → HTTP 500 configuration_error
├── AgentExecutionError         → HTTP 502 agent_execution_error
└── ExternalServiceError        → HTTP 503 external_service_error
```

- 领域层只表达错误语义，不返回 HTTP 响应。
- API 层集中映射状态码和面向客户端的稳定文案。
- 参数校验错误统一转换为 HTTP 422 `validation_error`。
- 框架 404/405 也转换为同一 `ErrorResponse` 结构。
- API 不返回堆栈、内部异常文本或完整输入数据。
- 服务端日志保留错误码、request_id、路径和必要的异常信息。
- 不静默吞掉异常：Agent 将异常转为失败结果并记录；Service 将失败结果转换为
  `AgentExecutionError`；API 统一记录并返回安全错误。

## 8. 日志与可观测性

使用标准库 `logging`，通过 `configure_logging()` 统一配置 `agentic_commerce_platform`
命名空间。默认控制台格式：

```text
2026-11-21T... | INFO | agentic_commerce_platform.agents.base | agent_completed | request_id=... agent_name=demo_agent duration_ms=0.18 attempt=1
```

`LOG_FORMAT=json` 时输出单行 JSON，可平滑接入后续日志采集。每条记录保证包含：

- `timestamp`
- `level`
- `logger`（模块名）
- `message`
- `request_id`
- `agent_name`

通过 `contextvars` 在中间件和 Agent 生命周期中自动注入关联字段，避免每个日志调用
重复传参。以下信息不进入日志：

- API Key 或任何凭据。
- 完整 Prompt。
- 完整用户上下文/画像。
- 请求体原文。
- 完整堆栈的 API 响应（只在服务端日志中记录）。

## 9. Agent 运行时

`BaseAgent` 统一处理：

- 名称与执行策略校验。
- 每次调用的计时。
- 开始、完成、失败日志。
- `asyncio.wait_for` 超时。
- 普通异常到失败 `AgentResult` 的转换。
- 统一的 `AgentResult.agent_name`/`latency_ms` 归一化。
- `_should_retry` 重试扩展点和退避等待。
- 取消（`CancelledError`）和解释器级异常不被吞掉。

子类只需实现 `execute()`。阶段一的 `DemoAgent` 不进行检索、排序或推荐。
`max_retries` 默认 0，`_should_retry` 默认不重试，后续可按 Provider 错误类型扩展。

## 10. LLM Provider 抽象

`LLMProvider` 是 `runtime_checkable` Protocol，核心方法：

```python
async def generate(
    self,
    prompt: str,
    *,
    system_prompt: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str: ...
```

`MockLLMProvider`：

- 不发起网络请求，不需要 API Key。
- 忽略 Prompt，返回固定文本，因此测试完全确定。
- 支持通过 `fail=True` 模拟失败并抛出 `ExternalServiceError`。
- 输出显式包含“MOCK、不是真实大模型、不包含真实商品推荐”。
- `build_llm_provider()` 是未来接入真实 Provider 的替换点。

## 11. RecommendationService

Service 负责用例级编排，路由不承载业务逻辑：

1. 接受已验证的 `RecommendationRequest`。
2. 创建或沿用 request_id。
3. 在请求日志上下文中调用 DemoAgent。
4. 检查 Agent 结果并在失败时抛出 `AgentExecutionError`。
5. 构造 `status=skeleton`、`products=[]` 的响应。
6. 记录 Agent 结果和端到端耗时。
7. 将未预期异常保留为 cause，交给 API 层安全返回。

阶段一响应中的 `agent_results` 非空，因为它真实执行了 DemoAgent + MockLLMProvider。
这是对验收示例中空 `agent_results` 的扩展，不代表真实推荐能力。

## 12. LangGraph 状态预留

`RecommendationState` 使用 `TypedDict(total=False)` 预留：

```python
request_id: str
user_id: str
scene: str
num_items: int
products: list[Product]
agent_results: dict[str, AgentResult]
errors: list[str]
```

当前没有安装 LangGraph，也没有 Supervisor、节点、边、图或 checkpoint。该类型仅作为
后续阶段的契约起点；未来节点可按需补充画像、检索候选、库存约束和人工审批字段。

## 13. 测试策略

- 单元测试隔离配置、模型、异常、Agent、Provider 和 Service。
- API 集成测试使用 FastAPI `TestClient`，不启动外部服务。
- 测试配置显式注入，API Key 为空，Provider 固定为 Mock。
- 使用 monkeypatch 阻断 `socket.create_connection`，验证请求链路无出站网络。
- 测试覆盖 422、404、502 的统一错误结构。
- 日志测试验证 request_id/agent_name、JSON 字段和敏感字段缺失。

## 14. 关键设计决策

| 决策 | 原因 |
| --- | --- |
| 使用标准 `logging` 而非引入 structlog | 阶段一依赖更少；JSON formatter 已满足后续扩展 |
| Domain 模型不允许额外字段 | 防止 API 契约漂移和未审查数据进入系统 |
| API 不返回内部异常文本 | 满足安全要求，便于稳定客户端错误处理 |
| 服务层负责 request_id 和计时 | 路由保持薄；Service 可被非 HTTP 入口复用 |
| DemoAgent 而非真实业务 Agent | 只验证基础设施，不提前实现阶段二 |
| Provider 工厂只允许 mock | 配置了不存在的 Provider 时快速失败，不静默降级 |
| 阶段一不接入 LangGraph | 避免为不存在的图引入依赖和伪实现 |
| 显式依赖组装放在 app factory | 便于测试注入，避免全局可变业务状态 |

## 15. 后续扩展建议

1. 在 `infrastructure` 增加真实 LLM Provider、商品仓储和向量检索适配器。
2. 在 `agents` 逐个增加用户画像、检索、推荐、库存、文案 Agent。
3. 在 `orchestration` 引入 LangGraph，并严格使用 `RecommendationState` 作为状态契约。
4. 增加数据库/缓存/向量库的生命周期管理和健康检查。
5. 增加 OpenTelemetry 或结构化事件表，记录 Agent 执行轨迹。
6. 增加离线评估数据集、指标和回归测试。
7. 引入 Human-in-the-loop 时，在图层面处理中断、恢复和审批状态。
