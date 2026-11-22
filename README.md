# agentic-commerce-platform

一个面向真实工程能力学习与求职展示的多 Agent 电商平台。本仓库当前只完成
**阶段一：工程骨架与基础设施**，不包含真实商品推荐、真实大模型调用或完整多 Agent
协作。

> **重要边界**
>
> - 当前 `POST /api/v1/recommend` 只是工程骨架，`status` 固定为 `skeleton`。
> - 当前不返回真实商品，`products` 始终为空。
> - 当前没有 Redis、MySQL、PostgreSQL、Milvus、Qdrant、Kafka 或 Prometheus。
> - 当前没有真实 LLM 调用，只使用完全离线的 `MockLLMProvider`。
> - 当前没有 Supervisor、LangGraph 图或多 Agent 协作，只有未来状态模型。
> - `agent_results` 中的输出是 Mock 输出，不是真实大模型结果。

## 阶段一目标

阶段一只建立一个可安装、可启动、可测试、可扩展的工程基础：

- 清晰的领域层、服务层、API 层和基础设施层边界。
- Pydantic v2 领域契约与项目级异常体系。
- 统一的结构化日志、request_id/agent_name 关联字段。
- 可复用的 `BaseAgent` 生命周期与统一 `AgentResult`。
- 与供应商解耦的 `LLMProvider` 接口和离线 Mock 实现。
- 最小 FastAPI 服务、健康检查与推荐接口骨架。
- 为未来 LangGraph 工作流预留状态类型。
- 不依赖外部网络的单元测试和 API 集成测试。

## 当前已实现

- Python 3.11+ 标准 `src` 布局，`pyproject.toml` 管理依赖。
- 基于 `pydantic-settings` 的环境变量与 `.env` 配置，包含校验和密钥保护。
- 严格校验的领域模型：`RecommendationRequest`、`Context`、`Product`、
  `AgentResult`、`RecommendationResponse`、`ErrorResponse`。
- 异常体系：`EcommercePlatformError`、`ConfigurationError`、
  `AgentExecutionError`、`ExternalServiceError`。
- 统一日志：时间、等级、模块、消息、`request_id`、`agent_name`；支持
  `console` 与 `json` 两种格式。
- `BaseAgent`：名称、计时、日志、异常转结构化结果、超时、可扩展重试钩子。
- `DemoAgent`：仅用于验证 API → Service → Agent → LLM Provider 链路。
- `LLMProvider` Protocol 与确定性的离线 `MockLLMProvider`。
- `GET /health` 健康检查。
- `POST /api/v1/recommend` 推荐接口骨架。
- `RecommendationService` 负责请求 ID、Agent 调用、计时、日志和异常转换。
- 统一错误 JSON，含 422 参数校验错误和 502 Agent 失败。
- `RecommendationState` TypedDict，仅为后续 LangGraph 预留。
- pytest 单元测试、FastAPI 集成测试。
- 阶段一架构与验收文档。

## 当前未实现

- 用户画像 Agent、商品检索 Agent、商品推荐 Agent、库存决策 Agent、营销文案 Agent。
- Supervisor、LangGraph 节点、图编译和检查点。
- RAG、向量检索、商品知识库。
- 长期记忆和用户画像存储。
- Human-in-the-loop。
- 真实 LLM API、真实 Prompt 管理、真实商品数据。
- Redis、关系数据库、向量数据库、消息队列。
- 指标、链路追踪、Prometheus 与自动评估体系。
- 鉴权、限流、生产级部署和 CORS 策略。

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
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── dependencies.py
│       │   ├── exception_handlers.py
│       │   ├── middleware.py
│       │   └── routes/
│       │       ├── __init__.py
│       │       ├── health.py
│       │       └── recommendation.py
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── demo.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── enums.py
│       │   ├── errors.py
│       │   └── models.py
│       ├── orchestration/
│       │   ├── __init__.py
│       │   └── state.py
│       ├── services/
│       │   ├── __init__.py
│       │   └── recommendation_service.py
│       └── infrastructure/
│           ├── __init__.py
│           ├── llm/
│           │   ├── __init__.py
│           │   ├── base.py
│           │   └── mock_provider.py
│           └── observability/
│               ├── __init__.py
│               └── logging.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_settings.py
│   │   ├── test_models.py
│   │   ├── test_base_agent.py
│   │   ├── test_mock_llm.py
│   │   └── test_recommendation_service.py
│   └── integration/
│       └── test_api.py
└── docs/
    ├── architecture.md
    └── phase-1-acceptance.md
```

### 相对建议结构的调整

- 增加 `agents/demo.py`：服务层需要调用一个明确标注为演示用途的 Agent，才能验证
  Agent 生命周期与 Provider 抽象；它不是业务 Agent。
- 增加 `api/dependencies.py`：把应用级依赖查找从路由中分离，便于测试覆盖。
- 增加 `api/exception_handlers.py`：统一异常到稳定 JSON 的映射，避免路由重复处理。
- 增加 `api/middleware.py`：集中处理 request_id、访问日志和计时响应头。
- 增加 `tests/conftest.py`：集中提供完全离线、空 API Key 的测试配置。
- 推荐接口实际会执行 `DemoAgent + MockLLMProvider`，因此 `agent_results` 不是空对象，
  `total_latency_ms` 为真实测得的耗时。这是对需求中“可以返回空 `agent_results`”
  示例的可解释扩展，仍保持 `status=skeleton` 和空商品列表。

## 环境要求

- Python 3.11 或更高版本
- 阶段一**不需要**任何数据库、Redis、向量库、消息队列、真实 LLM API Key 或网络调用

## 安装

```powershell
cd agentic-commerce-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

POSIX shell：

```bash
cd agentic-commerce-platform
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

只安装运行依赖（不安装 pytest/httpx）：

```bash
pip install -e .
```

## 环境变量

复制示例文件：

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `agentic-commerce-platform` | 应用名称，健康检查返回 |
| `APP_VERSION` | `0.1.0` | 应用版本 |
| `APP_ENV` | `development` | `development` / `test` / `production` |
| `DEBUG` | `false` | 生产环境必须为 `false` |
| `API_HOST` | `127.0.0.1` | 启动命令使用的主机 |
| `API_PORT` | `8000` | 1–65535 |
| `LOG_LEVEL` | `INFO` | 日志等级 |
| `LOG_FORMAT` | `console` | `console` 或 `json` |
| `LLM_PROVIDER` | `mock` | 阶段一仅允许 `mock` |
| `LLM_API_KEY` | 空 | 阶段一不需要；`SecretStr` 保护，不写入日志 |
| `LLM_BASE_URL` | 空 | 阶段一不使用 |
| `LLM_MODEL` | `mock-llm-v1` | 未来 Provider 使用的模型标识 |

配置在进程启动时校验。非法环境、端口、日志等级、Provider 或
`production + debug=true` 会快速失败。测试使用显式构造的配置，不读取外部服务。

## 启动

```bash
uvicorn agentic_commerce_platform.api.app:app --host 127.0.0.1 --port 8000 --reload
```

也可以使用模块方式：

```bash
python -m uvicorn agentic_commerce_platform.api.app:app --reload
```

启动后可访问：

- API 文档：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>
- 健康检查：<http://127.0.0.1:8000/health>

## API 示例

### 健康检查

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

### 阶段一推荐接口骨架

```bash
curl -X POST http://127.0.0.1:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: demo-request-1" \
  -d '{
    "user_id": "demo-user",
    "scene": "home",
    "num_items": 3,
    "context": {
      "device_type": "mobile",
      "locale": "zh-CN",
      "keywords": ["python"]
    }
  }'
```

响应示意（`latency` 数值每次运行会变化）：

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
      "latency_ms": 0.18,
      "error": null,
      "confidence": null,
      "data": {
        "phase": "phase-1",
        "demo": true,
        "provider": "mock",
        "llm_output": "【MOCK LLM】这是离线模拟输出，不是真实大模型生成内容，也不包含真实商品推荐。",
        "disclaimer": "DemoAgent + MockLLMProvider output only; not a real recommendation and not a real LLM result."
      }
    }
  },
  "total_latency_ms": 0.31
}
```

`X-Request-ID` 若符合安全格式会被沿用；否则服务会自动生成 UUID，并在响应头返回。
该 ID 同时进入日志和响应体。

### 参数校验失败

```json
{
  "request_id": "generated-request-id",
  "error": {
    "code": "validation_error",
    "message": "请求参数校验失败。",
    "details": {
      "errors": [
        {
          "loc": "body.user_id",
          "message": "Field required",
          "type": "missing"
        }
      ]
    }
  }
}
```

### Agent 失败

```json
{
  "request_id": "failure-request-1",
  "error": {
    "code": "agent_execution_error",
    "message": "推荐 Agent 执行失败，请稍后重试。",
    "details": null
  }
}
```

API 不返回堆栈或内部异常文本；完整原因只记录在服务端日志中。

## 测试

```bash
pytest -q
```

如果当前环境没有把虚拟环境的脚本目录加入 `PATH`，使用等价命令：

```bash
python -m pytest -q
```

测试覆盖：

- Settings 默认值、环境变量、`.env`、非法配置和 API Key 脱敏。
- 领域模型正常与非法输入。
- `BaseAgent` 成功、异常、超时和重试扩展点。
- `MockLLMProvider` 成功、失败与确定性输出。
- `RecommendationService` 骨架响应、请求 ID、Agent 失败转换。
- `/health`、`/api/v1/recommend`、422、稳定错误结构、404。
- 全程不访问外部网络，不需要 API Key、Redis、数据库或向量数据库。

本机实际执行结果：**67 passed, 1 warning in 0.47s**。唯一 warning 是第三方
FastAPI/Starlette TestClient 对当前 `httpx` 版本的弃用提示，不是测试失败。
完整记录（含网络受限下的依赖安装说明）见
[阶段一验收文档](docs/phase-1-acceptance.md)。

## 阶段一验收标准

- [ ] 在全新空环境中从公网执行 `pip install -e ".[dev]"`：本机网络/证书受限，
  未完成该在线安装验证；可编辑安装、依赖声明与构建配置已验证，详见验收文档。
- [x] `pytest -q` 全部通过（67 passed），且不需要外部服务或 API Key。
- [x] `GET /health` 返回应用名、版本、环境和 `healthy`。
- [x] `POST /api/v1/recommend` 返回 `status=skeleton`、空商品列表、显式 Mock 说明。
- [x] 请求校验失败返回 422 和稳定错误结构。
- [x] Agent 失败返回 502 和稳定错误结构，不泄露堆栈。
- [x] 日志包含 request_id/agent_name，且不包含 API Key 或完整上下文。
- [x] 当前能力边界在 README、架构文档和接口响应中均有明确说明。

## 后续阶段规划

1. **阶段二：真实检索与推荐 Agent**：商品仓储接口、检索 Agent、推荐 Agent、
   排序与评分、离线商品数据。
2. **阶段三：用户画像与长期记忆**：画像模型、偏好抽取、记忆存储与更新策略。
3. **阶段四：Supervisor 与 LangGraph**：图节点、路由、并行调用、状态合并、失败降级。
4. **阶段五：RAG 与库存决策**：商品/知识库检索、库存 Agent、约束决策。
5. **阶段六：Human-in-the-loop 与营销文案**：人工审批、可中断工作流、文案生成。
6. **阶段七：可观测性与评估**：执行轨迹、指标、追踪、评估数据集与自动回归。
7. **阶段八：生产基础设施**：数据库、Redis、向量数据库、消息队列、鉴权与部署。

## 设计文档

- [阶段一架构说明](docs/architecture.md)
- [阶段一验收记录](docs/phase-1-acceptance.md)
