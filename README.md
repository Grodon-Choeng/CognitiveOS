# CognitiveOS

CognitiveOS 是一个面向个人助理场景的 AI-native 模块化单体后端。

当前仓库处于第一阶段骨架期，优先服务 reminder 垂直切片：

`reminder creation` → `persistence` → `Temporal workflow bootstrap` → `message sending adapter contract` → `user reply continuation path`

## 当前技术基线

- Web 层：`FastAPI`
- Workflow 层：`Temporal`
- 数据层：`PostgreSQL` + `SQLAlchemy 2.x` + `Alembic`
- 模型访问：统一走 `llm_gateway`
- Agent 执行：统一走 `agent_runtime`
- Tool 执行：统一走 `tool_runtime`
- 基础工程：`Python 3.12+`、`uv`、`pytest`、`ruff`、`mypy`

## 本地启动

### 常用命令

```bash
make help
```

常用目标包括：

- `make install`
- `make infra-up`
- `make migrate`
- `make api`
- `make worker`
- `make fmt`
- `make check`

### 1. 安装依赖

```bash
make install
```

### 2. 准备环境变量

```bash
cp .env.example .env
```

应用会默认读取项目根目录下的 `.env`。

### 3. 启动本地基础设施

```bash
make infra-up
```

本地默认会启动：

- PostgreSQL：`localhost:5432`
- Redis：`localhost:6379`
- Temporal gRPC：`localhost:7233`
- Temporal UI：`http://localhost:8080`
- Temporal 动态配置文件：`dynamicconfig/development-sql.yaml`

### 4. 执行数据库 migration

```bash
make migrate
```

### 5. 启动 HTTP 服务

```bash
make api
```

### 6. 启动 Temporal worker

```bash
make worker
```

### 7. Temporal 前置条件

- 当前仓库已接入真实的 Temporal client / workflow signal 链路。
- 默认本地编排已经提供 Temporal server 与 Temporal UI。
- 启动 API 或 worker 前，请先确保 `COGNITIVE_OS_TEMPORAL_HOST` 指向可用的 Temporal server；若使用默认编排，则保持 `localhost:7233` 即可。

## 当前目录骨架

```text
app/
  api/
  application/
  bootstrap/
  config/
  domain/
  infrastructure/
  observability/

tests/
  unit/
  integration/
  workflow/
```

## 说明

- 当前配置会默认读取 `.env`，因此复制完成后即可直接本地运行。
- 所有大模型调用都应通过统一记录机制留痕，默认同时写入数据库表 `model_invocation_logs` 与 `logs/model_invocations.jsonl`。
- 所有工具调用也应通过统一记录机制留痕，默认同时写入数据库表 `tool_invocation_logs` 与 `logs/tool_invocations.jsonl`。
- 当前 reminder create / reply 路由已预留，但仍是占位实现。
- 数据库、Temporal、消息发送适配器都已补齐骨架与契约，后续可在此基础上继续实现。
- 更详细的技术立场见 `docs/tech-decisions.md`。
