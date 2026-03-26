# CognitiveOS

CognitiveOS 是一个面向个人助理场景的 AI-native 模块化单体后端。

## 当前状态

当前仓库已经不是“第一阶段骨架期”。更准确的状态是：

- `reminder` 垂直切片已经闭环，能完成创建、持久化、Temporal 启动、发送、用户回复续跑。
- `conversation` 主链路已经切到 assistant kernel pipeline，但仍处于收敛期，而不是最终完成态。
- 仓库里仍保留少量过渡性兼容路径，例如 reminder reply fast path 和 legacy conversation adapter；这些路径的目标是兼容旧入口，不是继续承接新能力。

### 当前真实实现

当前 canonical path 由 `ConversationApplicationService` + `ConversationKernelFacade` 驱动，处理顺序是：

`resolve context` → `reminder fast path` → `build turn state` → `plan` → `execute` → `render` → `record / persist`

当前稳定可工作的纵向链路是：

`reminder creation` → `persistence` → `Temporal workflow bootstrap` → `message sending adapter contract` → `user reply continuation path`

### 当前收敛中的过渡点

- `ReminderConversationHandler` 仍会在高置信 reminder reply 上优先 shortcut，但低置信、拒绝、改期等情况会回到 kernel 主流程。
- `LegacyIntentConversationHandler` 仍保留旧入口兼容，但它只是转发到 kernel facade 的 adapter，不是系统的能力增长点。
- 对象解析正在统一收口到 kernel resolver；service 层不再作为自然语言引用的主入口。

### 下一阶段目标

- 继续收口 conversation 主路径，让 assistant kernel 成为更完整、可稳定回归的唯一行为规范。
- 继续清理迁移期 compatibility path / shortcut，而不是提前宣称“所有终态都已完成”。

## 当前技术基线

- Web 层：`FastAPI`
- 依赖注入 / 运行时装配：`Dishka`
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
- `make services-up`
- `make services-status`
- `make services-stop`
- `make services-restart`
- `make image-build`
- `make image-up`
- `make image-down`
- `make image-logs`
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

仓库默认通过项目级 `uv` 配置和 `Makefile` 环境变量使用阿里云 PyPI 镜像：

- `https://mirrors.aliyun.com/pypi/simple`
- 如需临时覆盖，可在命令前显式指定 `UV_DEFAULT_INDEX=...`

### 2. 准备环境变量

```bash
cp .env.example .env
```

应用会默认读取项目根目录下的 `.env`。

当前 LLM 配置建议分成两层：

- 默认兜底配置
  - `COGNITIVE_OS_LLM_DEFAULT_PROVIDER`
  - `COGNITIVE_OS_LLM_DEFAULT_ENDPOINT`
  - `COGNITIVE_OS_LLM_DEFAULT_API_KEY`
  - `COGNITIVE_OS_LLM_DEFAULT_SMALL_MODEL`
  - `COGNITIVE_OS_LLM_DEFAULT_LARGE_MODEL`
- conversation 覆盖配置
  - `COGNITIVE_OS_CONVERSATION_LLM_PROVIDER`
  - `COGNITIVE_OS_CONVERSATION_LLM_ENDPOINT`
  - `COGNITIVE_OS_CONVERSATION_LLM_API_KEY`
  - `COGNITIVE_OS_CONVERSATION_INTENT_MODEL`

当前实现里：

- `LLM_DEFAULT_SMALL_MODEL` 会作为 conversation intent 的默认兜底模型
- `LLM_DEFAULT_LARGE_MODEL` 先作为未来动态路由的保留配置
- conversation 层如果显式提供自己的 provider / endpoint / key / model，会优先覆盖默认配置
- 本地 `local` provider 仍允许不配置 key
- 外部 `openai` / OpenAI-compatible provider 通常需要同时配置 endpoint、key、model
- 进程日志默认会额外写入 `COGNITIVE_OS_LOG_DIR`，文件名按 `process_role` 拆分，例如 `logs/api.log`、`logs/worker.log`

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
- 若只使用飞书长连接接收入站事件，当前只需要 `FEISHU_APP_ID` 与 `FEISHU_APP_SECRET`

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

### 8. 使用统一服务编排命令

如果你希望把 `infra`、`migrate`、`api`、`worker` 串起来统一启动，推荐直接使用：

```bash
make services-up
```

默认会按顺序执行：

`infra -> migrate -> api -> worker`

常见用法示例：

```bash
make services-status
make services-stop
make services-restart
make services-up SERVICES=api,worker API_RELOAD=1
make services-up SERVICES=infra,migrate,api
```

说明：

- `SERVICES` 支持 `all` 或逗号分隔列表，可选值包括：`infra`、`migrate`、`api`、`worker`、`feishu-longconn`
- `API_RELOAD=1` 当前只对 `api` 生效，会以 `uvicorn --reload` 启动
- 服务编排器会把常驻服务状态与分进程日志写到 `.runtime/services/`
- 日志按进程拆分保存，例如 `.runtime/services/logs/api.log`、`.runtime/services/logs/worker.log`
- API / worker / 长连接进程日志会统一带上 `trace_id`、`chain_id`、`request_id`、`service_run_id`，便于串联完整处理链路

### 9. 构建镜像并在容器中运行

如需把当前应用打包成镜像并在容器中运行，可使用：

```bash
make image-build
make image-up
```

常见命令：

```bash
make image-build APP_IMAGE=cognitiveos-app:latest
make image-migrate
make image-up IMAGE_SERVICES="app-api app-worker app-feishu-longconn"
make image-up IMAGE_SERVICES="app-api app-worker"
make image-logs
make image-down
```

说明：

- `image-up` 会自动拉起基础设施、构建镜像、执行 migration，再启动容器化服务
- 默认容器服务为 `app-api`、`app-worker` 与 `app-feishu-longconn`
- 如果只想启动部分容器，可通过 `IMAGE_SERVICES` 覆盖默认值
- 同一个镜像会被 `app-api`、`app-worker`、`app-feishu-longconn`、`app-migrate` 复用
- `./logs:/app/logs` 会挂载到容器内，因此应用日志文件、`message/model/tool/workflow` 的 jsonl 都会保存在宿主机 `logs/` 目录
- Docker 自身 stdout/stderr 日志也仍可通过 `docker compose logs` 或 `make image-logs` 查看
- `.dockerignore` 已排除 `.venv`、`tests`、`.runtime`、`logs` 等本地运行产物，避免镜像上下文膨胀
- 若容器内仍使用 `local` provider，注意 `localhost` 指向容器自身；需要把 `COGNITIVE_OS_LOCAL_LLM_BASE_URL` 或默认 LLM endpoint 改成容器内可达的地址

### 10. Temporal 前置条件

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

## Assistant Execution Kernel（P0）

当前 `app/application/conversations/kernel/` 负责 assistant 对话执行内核，重点先把这三件事做好：

- `ReferenceResolver`
  - 统一解析 `这个 / 那个 / 第二个 / 买药那个`
- `ActionPlan -> Executor`
  - 把理解、执行、回复拆开，不再在一个 handler 里硬编码到底
- `AssistantResponseRenderer`
  - 把回复从“接口感”改成更自然的助手表达

### 当前支持的话术示例

- `明天早上九点提醒我打卡`
- `查看待办`
- `完成第二个`
- `取消买药那个提醒`
- `记一下我不喜欢早上八点前提醒`
- `看看今天还有什么`
- `把这个提醒改到明天九点`
- `这个待办明天早上提醒我`
- `改成待办`
- `重试失败提醒`

### 当前范围说明

- reminder reply continuation 仍保留优先快路径，但现在只有高置信 acknowledge 才会直接 shortcut；改期、拒绝和低置信命中不会自动 completed
- 当前 turn state 已持久化到 `assistant_turn_states`
- 已支持 task/reminder 双向转换、失败提醒重试和 conversation debug 返回
- memory 已支持 `memory_type`、`scope_object_type`、`scope_object_id`、`importance`、`expires_at`

### 当前主链路与迁移期术语

- canonical path：`ConversationApplicationService` + `ConversationKernelFacade`
- legacy adapter：`LegacyIntentConversationHandler`（保留 `IntentConversationHandler` 兼容别名）
- object resolution：自然语言对象解析以 kernel resolver 为主入口；service 层只保留中性查询能力与少量待迁移兼容接口
- 当前 `ConversationApplicationService._handle_with_kernel()` 的真实顺序是：
  - `resolve context`
  - `reminder fast path`
  - `build turn state`
  - `plan`
  - `execute`
  - `render`
  - `record / persist assistant_turn_state`
- `resolve target` 当前仍属于 executor / resolver 内部职责，不再作为顶层阶段单列

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
- 现已提供统一服务编排命令：`make services-up` / `make services-stop` / `make services-status` / `make services-restart`，便于串联启动 `infra`、`migrate`、`api`、`worker` 等服务。
- 服务编排器当前会把常驻服务 PID 状态与分进程日志写到 `.runtime/services/`，用于检测服务是否已在运行、停止与重启。
- 这些进程日志默认会带上统一链路标识，便于结合 `message/model/tool/workflow` 审计记录回溯一条请求在不同进程中的执行过程。
- 现已支持通过 `Dockerfile` + `compose.yaml` 构建单镜像并启动 `app-api` / `app-worker` / `app-feishu-longconn` / `app-migrate`；容器内 `logs/` 目录默认映射回宿主机。
- 内部统一消息入口为 `POST /api/v1/conversations/messages`，用于让 Web 与飞书共用同一条 conversation 处理链路。
- 现已新增 `debug_im` 调试渠道：`POST /api/v1/debug/im/messages` 可模拟用户发消息，`GET /api/v1/debug/im/messages` / `GET /api/v1/debug/im/sessions` 可查看最近消息与会话。
- `WS /api/v1/debug/im/ws?user_identity=...` 可订阅调试 IM 会话的实时消息；连接后会先收到最近历史，再持续收到新消息推送。
- `debug_im` 仍复用同一条 conversation / reminder / Temporal / messaging adapter 主链路，不单独维护第二套业务逻辑。
- conversation source binding 当前使用数据库唯一约束 + upsert 写入，避免并发场景下为同一来源键写出重复映射。
- conversation assistant kernel 当前会在入站消息审计 metadata 中附带结构化 `assistant_turn_state`，用于复用上一回合的焦点对象、候选列表和最近动作。
- assistant turn state 现在也会双写到数据库表 `assistant_turn_states`，用于 webhook / 长连接 / 多轮异步对话下的稳定恢复。
- 统一审计查询入口为 `GET /api/v1/audit/events`，支持按 `kind`、`conversation_id`、`session_id`、`success`、`channel`、`provider`、`tool_name`、`workflow_type`、时间范围与游标分页查询 `message/model/tool/workflow` 四类事件。
- 聚合时间线入口为 `GET /api/v1/audit/timeline`，会把 `message/model/tool/workflow` 四类事件按时间混排返回。
- 聚合时间线的游标当前带有事件类型信息，用于避免不同审计表在同一时间戳下分页时出现跨类型漂移。
- 当前最小入站续执行逻辑：仅对飞书 `p2p` 文本消息生效，并按 `sender_open_id` 关联该用户最近一个 `pending` reminder。
- `debug_im` 的 reminder 续执行不依赖飞书长连接；提醒发出后会以调试消息形式写入统一消息审计与实时 websocket 推送，可直接在同一调试会话里回复。
- conversation intent 当前改为 `LLM 优先、规则兜底`：若配置了 `COGNITIVE_OS_CONVERSATION_INTENT_MODEL`，会优先走 `llm_gateway` 做 reminder/task/memory 意图识别；若未单独配置 conversation 模型，则会回退到 `COGNITIVE_OS_LLM_DEFAULT_SMALL_MODEL`；provider / endpoint / key 也遵循“conversation 覆盖优先、默认配置兜底、旧 provider 专属配置兼容”的顺序；未配置或模型失败时再退回显式规则。
- 在 assistant kernel 内部，当前规划阶段会优先尝试显式规则快路径，再复用已有 classifier 与 fallback responder。
- reminder 的规则兜底当前保持收敛：只覆盖显式、低歧义的输入，例如 `提醒：2026-03-24T09:00:00+08:00 开会`；更自然的时间表达默认优先交给 `LLM` 处理。
- 当前 reminder create / list / get / reply / cancel 路由已接入 application service，可用于最小 reminder 生命周期闭环验证。
- 已支持 `GET /api/v1/reminders` 查看提醒列表、`GET /api/v1/reminders/{reminder_id}` 查询状态，以及 `POST /api/v1/reminders/{reminder_id}/cancel` 主动取消 pending reminder。
- 已支持 `POST /api/v1/reminders/{reminder_id}/reschedule` 改期 pending / failed reminder，并可同时更新提醒文案。
- `GET /api/v1/reminders` 现在也支持 `query` 关键词过滤，便于按内容搜索当前会话里的提醒。
- 已支持 `POST /api/v1/memories` 写入记忆、`GET /api/v1/memories` 查询记忆列表、`GET /api/v1/memories/{memory_id}` 点查记忆，以及 `POST /api/v1/memories/{memory_id}/archive` 归档记忆。
- 已支持 `POST /api/v1/tasks` 创建任务、`GET /api/v1/tasks` 查询任务列表、`GET /api/v1/tasks/{task_id}` 点查任务，以及 `POST /api/v1/tasks/{task_id}/complete` / `POST /api/v1/tasks/{task_id}/cancel` 完成或取消任务。
- `GET /api/v1/tasks` 现在也支持 `query` 关键词过滤，便于按标题搜索当前会话里的任务。
- 已支持 `GET /api/v1/overview` 聚合查看当前会话的 pending reminders、pending tasks、active memories，以及 recent activity。
- conversation 对话入口现在也支持 `查看概览` / `今天有什么` 之类的概览动作，并会自动回一条聚合结果消息。
- conversation 对话入口还支持 `查看最近活动`，会返回当前会话最近的统一审计时间线片段。
- conversation 查询现在也支持按状态查看，例如：`查看已完成任务`、`查看已取消提醒`、`查看已归档记忆`。
- reminder 查询在 conversation 中现在也支持 `查看失败提醒`，便于排查工作流启动失败后留下的提醒记录。
- conversation 查询现在还支持 `搜索任务 xxx`、`搜索提醒 xxx` 这类关键词检索。
- memory 列表查询现在还支持 `query` 关键词过滤；conversation 里也支持 `搜索记忆 xxx` 这种读取方式。
- conversation 现在支持把 task 转成 reminder、把 reminder 改成 task，以及对 failed reminder 发起重试。
- `POST /api/v1/reminders/{reminder_id}/retry` 已支持对失败提醒进行重试。
- `POST /api/v1/conversations/messages?debug=true` 会返回 turn state、plan、execution result 等调试信息。
- 当 conversation 无法识别输入时，也会自动返回一条引导提示，而不是静默无响应。
- conversation 对话入口现在还支持最小动作类命令：`完成任务` / `取消任务` 会作用于当前会话最近一条 pending task，`归档记忆` 会归档当前会话最近一条 active memory，`取消提醒` 会取消当前会话最近一条 pending reminder。
- 当这些动作当前没有可操作对象时，系统会直接返回用户可读反馈，而不是静默失败。
- 这些动作现在也支持附带内容提示，例如：`完成任务 纪要`、`取消提醒 打卡`、`归档记忆 九点提醒`，系统会优先按提示命中对象。
- 统一 conversation 入口当前还支持显式口令分流：`待办：...` / `todo: ...` 会创建 task，`记住：...` / `记一下：...` 会写入 memory；reminder 续执行仍优先于这些规则。
- `POST /api/v1/reminders` 当前也支持显式传入 `dispatch_chat_id` 与 `dispatch_thread_id`，便于通过 HTTP 创建群聊 / 话题内 reminder。
- reminder 与 conversation 入口中，`thread_id` 不能脱离对应的 `chat_id` 单独提供，避免写入不可解析的线程上下文。
- `remind_at` 当前要求显式带时区；`text` 类型的 conversation 消息也必须提供非空 `text` 内容。
- reminder 创建阶段若 Temporal 工作流启动失败，当前会把 reminder 标记为 `failed`，并通过 HTTP `503` 返回错误，避免留下“仍是 pending 但实际不可继续”的脏状态。
- 数据库、Temporal、消息发送适配器都已补齐骨架与契约，后续可在此基础上继续实现。
- 更详细的技术立场见 `docs/tech-decisions.md`。
- assistant conversation 结构与分期范围见 `docs/architecture.md` 与 `docs/mvp.md`。
