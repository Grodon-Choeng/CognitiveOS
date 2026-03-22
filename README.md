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
- 若需要使用飞书发送消息，还需要配置 `FEISHU_APP_ID` 与 `FEISHU_APP_SECRET`
- 若需要接收飞书事件订阅回调，还需要配置 `FEISHU_VERIFICATION_TOKEN`；如果飞书事件订阅启用了加密，还需要配置 `FEISHU_ENCRYPT_KEY`

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

### 7. 启动飞书长连接监听

```bash
make feishu-longconn
```

### 8. Temporal 前置条件

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
- 所有用户消息收发也应通过统一记录机制留痕，默认同时写入数据库表 `message_event_logs` 与 `logs/message_events.jsonl`。
- 消息事件留痕当前还会记录适配器名称、处理耗时，以及入站消息是否被业务链路接管。
- 所有 workflow 关键事件也应通过统一记录机制留痕，默认同时写入数据库表 `workflow_event_logs` 与 `logs/workflow_events.jsonl`。
- 飞书已作为可选 IM 发送入口接入，当前通过 `MessagingAdapter` 边界统一发送。
- 飞书事件订阅回调入口为 `POST /api/v1/integrations/feishu/events`。
- 飞书也支持通过长连接接收入站事件，入口命令为 `make feishu-longconn`。
- 内部统一消息入口为 `POST /api/v1/conversations/messages`，用于让 Web 与飞书共用同一条 conversation 处理链路。
- 统一审计查询入口为 `GET /api/v1/audit/events`，支持按 `kind`、`conversation_id`、`session_id`、`success`、`channel`、`provider`、`tool_name`、`workflow_type`、时间范围与游标分页查询 `message/model/tool/workflow` 四类事件。
- 聚合时间线入口为 `GET /api/v1/audit/timeline`，会把 `message/model/tool/workflow` 四类事件按时间混排返回。
- 当前最小入站续执行逻辑：仅对飞书 `p2p` 文本消息生效，并按 `sender_open_id` 关联该用户最近一个 `pending` reminder。
- 当前 reminder create / reply 路由已接入 application service，可用于最小 reminder 创建与回复闭环验证。
- `POST /api/v1/reminders` 当前也支持显式传入 `dispatch_chat_id` 与 `dispatch_thread_id`，便于通过 HTTP 创建群聊 / 话题内 reminder。
- reminder 创建阶段若 Temporal 工作流启动失败，当前会把 reminder 标记为 `failed`，并通过 HTTP `503` 返回错误，避免留下“仍是 pending 但实际不可继续”的脏状态。
- 数据库、Temporal、消息发送适配器都已补齐骨架与契约，后续可在此基础上继续实现。
- 更详细的技术立场见 `docs/tech-decisions.md`。
