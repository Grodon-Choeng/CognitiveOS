# CognitiveOS 技术选型决策书 v1

## 1. 项目目标

CognitiveOS 是一个面向个人助理场景的 AI-native 系统，第一阶段聚焦以下能力：

- 对话驱动的任务创建
- 提醒与延迟提醒
- 等待用户回复后继续执行
- 简单记忆写入与读取
- 后续可扩展至 IM、日历、邮件、工具系统接入
- 本地调试场景下，允许接入一个最小 `debug_im` 渠道，用于在真实 IM 长连接被占用时继续验证消息收发闭环

第一阶段不追求“大而全”，而是优先打通一个最小闭环：

> 用户输入一句话 → 系统理解意图 → 创建可持久化任务/提醒 → 到时触发 → 用户回复 → 状态推进或关闭

---

## 2. 设计原则

### 2.1 总体原则

- 模块化单体优先
- 领域边界优先于框架便利
- 先跑通核心闭环，再扩能力面
- 对变化快的外部依赖做隔离
- 对核心基础设施接受适度绑定
- 全程面向 AI coding 友好性设计

### 2.2 AI coding 约束原则

本项目技术选型必须满足：

- 文档清晰
- 语义稳定
- 样例多
- 错误易定位
- 易于增量修改
- 适合通过仓库文档和约束文件驱动

---

## 3. 最终技术选型

### 3.1 Web 层

#### 选择

- FastAPI
- Dishka（用于依赖注入与运行时装配）

#### 选择理由

- Python 生态中成熟、主流、AI 生成成功率高
- 路由、依赖注入、请求响应模型都比较明确
- 非常适合作为“稳定底盘”
- 通过 Dishka 管理 app/request 级生命周期后，可以把装配逻辑继续收敛在 bootstrap 层，而不把全局 service locator 扩散到业务代码

#### 不选其他方案的原因

- 不在第一阶段引入更小众或更实验性的 Web 框架
- 风险预算应留给 `workflow / agent / tool` 这一层，而不是 API 框架本身

---

### 3.2 Workflow 层

#### 选择

- Temporal

#### 选择理由

CognitiveOS 的核心问题不是普通 CRUD，而是：

- 定时触发
- 长时间等待
- 根据用户回复继续
- 可恢复执行
- 多轮状态推进
- 失败后重试和恢复

这些都是 Temporal 的强项。

因此不自己手写任务状态机，不自己拼接“数据库 + 定时器 + 队列 + 回调”方案。

#### 原则

- 直接使用 Temporal 的核心语义
- 只做薄封装
- 不做伪通用 workflow 抽象层

---

### 3.3 Tool 协议层

#### 选择

- MCP-compatible internal contract

#### 选择理由

- 后续工具系统、外部服务、内部能力都需要统一接入边界
- 先按 MCP-compatible 设计，后面接 MCP server 或做兼容都更顺
- tool 层是长期资产，应该独立于某家模型 SDK 或某个 agent 框架

#### 原则

- 内部统一 tool schema
- tool registry 独立
- tool execution 独立
- tool auth / timeout / retry / tracing 独立

---

### 3.4 Agent 层

#### 决策

- 不让 LangChain / LangGraph / 厂商 SDK 直接进入业务层
- 不把任何外部 agent 框架视为业务核心
- 构建自己的轻量 `agent_runtime` 抽象
- 模型接入统一经 `llm_gateway`
- 第一阶段可优先使用 LiteLLM 作为模型网关

#### 理由

- 模型提供商会变
- agent 框架会变
- tool 协议可能演进
- workflow 语义则是核心基础设施，不宜过度抽象

因此 agent 层要做的是：

- 统一输入输出
- 隔离外部框架差异
- 让业务层不感知具体 SDK

而不是把所有 agent 框架当成业务逻辑的一部分。

---

### 3.5 模型层

#### 选择

- LiteLLM 为主入口
- 某些特殊能力允许 provider-native SDK 补充
- 所有入口统一收敛到 `llm_gateway`

#### 原则

- 业务层不能直接 `import` 某家 SDK
- 所有模型调用必须结构化
- 统一处理异常、日志、耗时、token、成本统计
- 后续切换模型厂商时，尽量不影响应用层与领域层
- 配置层应允许声明默认兜底模型配置（provider / endpoint / key / small model / large model），再由具体场景按需覆盖，给未来“小模型处理简单任务、大模型处理复杂任务”的动态路由预留空间

---

### 3.6 数据层

#### 选择

- PostgreSQL
- SQLAlchemy 2.x
- Alembic

#### 原则

- 数据模型与领域模型分离
- ORM 不直接渗透到 `domain`
- migration 正式管理
- 不使用高度魔法化的 ORM 封装

---

### 3.7 基础工程

#### 选择

- Python 3.12+
- `uv`
- `pytest`
- `ruff`
- `mypy`

#### 原则

- 类型优先
- 测试优先于“功能看起来可跑”
- `lint / type / test` 是完成定义的一部分

---

### 3.8 可观测性

#### 需要从第一天具备

- structured logging
- tracing
- workflow 执行日志
- LLM 请求日志
- tool 执行日志
- 集成调用日志

#### 原则

AI 系统最怕“看起来做了事，但不知道为什么这么做”。

所以 tracing 和 execution logs 不是后补项，而是基础设施。

---

### 3.9 Assistant Execution Kernel

#### 决策

- 在 `app/application/conversations/kernel/` 内建立 assistant execution kernel
- conversation 主链路采用：
  - `resolve context`
  - `reminder fast path`
  - `build turn state`
  - `plan`
  - `execute`
  - `render`
  - `record / persist`
- `resolve target` 作为 executor / resolver 内部职责，不再作为顶层阶段单列
- reminder continuation 继续保留优先快路径，但只处理高置信 acknowledge

#### 选择理由

当前 conversation 入口已经不仅是“分类后调一个 service”，而是需要解决：

- 当前回合上下文组装
- 对象引用解析
- 动作规划归一化
- 执行结果结构化
- 回复自然语言渲染

如果继续把这些逻辑混在单个 handler 里，会导致：

- 理解、执行、回复强耦合
- task/reminder/memory 只能平行发展，不能共享“助手”的交互体验
- `这个 / 那个 / 第二个` 这类高频表达无法稳定演进

因此 conversation 需要一个清晰的 application-layer kernel，而不是继续堆叠更大的 if/else handler。

#### 边界约束

- `ConversationContextResolver` 仍只负责 conversation/session binding
- 对象级引用解析不下沉到 infrastructure
- 不围绕 Temporal 造新的 workflow facade
- 当前已引入 `assistant_turn_states` 持久化表，用于保存多轮对话执行态；消息审计 metadata 继续保留为审计快照

#### 衍生决策

- task / reminder 的互转由 conversation executor 编排，具体持久化字段落在各自 service / repository
- failed reminder 的恢复不另造新 workflow 抽象，仍直接复用现有 reminder workflow gateway
- conversation debug 信息通过 `POST /api/v1/conversations/messages?debug=true` 暴露，不单独开辟第二套 handler 链路

---

## 4. 最终架构立场

可以概括成一句话：

> FastAPI 负责稳定对外接口，Temporal 负责长生命周期执行，MCP-compatible tool layer 负责工具统一接入，LLM/Agent 通过自定义 gateway 与 runtime 隔离外部依赖。

---

## 5. 哪些依赖需要“包一层”

### 5.1 必须包一层的

#### LLM provider

例如：

- OpenAI
- Anthropic
- Qwen
- GLM
- OpenRouter
- LiteLLM

统一通过：

- `llm_gateway`

#### Agent 框架或推理执行器

例如：

- LiteLLM-based execution
- OpenAI SDK
- LangGraph
- 未来其他 agent runtime

统一通过：

- `agent_runtime`

#### Tool 执行系统

统一通过：

- `tool_runtime`

#### 外部系统接入

例如：

- IM
- Email
- Calendar
- Webhook
- Notion / GitHub

统一通过：

- `integration_adapters`

---

### 5.2 不应过度抽象的

#### Temporal

只做薄封装，不做通用 workflow facade。

#### FastAPI

保留其原生使用方式，不构造额外的“二次框架”。

---

## 6. 推荐目录结构

```text
app/
  api/
    http/
      routes/
        health.py
        conversations.py
        reminders.py
        tasks.py
      schemas/
        common.py
        conversation.py
        reminder.py
        task.py
      deps/
        auth.py
        db.py
        services.py
      errors/
        handlers.py

  application/
    conversations/
      service.py
      commands.py
      queries.py
      dto.py
    reminders/
      service.py
      commands.py
      queries.py
      dto.py
    tasks/
      service.py
      commands.py
      queries.py
      dto.py
    memory/
      service.py
      dto.py
    agents/
      service.py
      dto.py

  domain/
    conversations/
      entities.py
      value_objects.py
      policies.py
      repository.py
    reminders/
      entities.py
      value_objects.py
      policies.py
      repository.py
    tasks/
      entities.py
      value_objects.py
      policies.py
      repository.py
    memory/
      entities.py
      value_objects.py
      repository.py
    shared/
      enums.py
      errors.py
      events.py
      types.py

  infrastructure/
    db/
      models/
        conversation.py
        reminder.py
        task.py
        memory.py
      repositories/
        conversation_repo.py
        reminder_repo.py
        task_repo.py
        memory_repo.py
      session.py
      base.py

    llm/
      gateway.py
      models.py
      errors.py
      providers/
        litellm_provider.py
        openai_provider.py
        anthropic_provider.py
        qwen_provider.py

    agents/
      runtime.py
      models.py
      implementations/
        default_runtime.py

    tools/
      runtime/
        executor.py
        dispatcher.py
      registry/
        registry.py
      mcp/
        protocol.py
        adapters.py
      builtins/
        reminder_tools.py
        calendar_tools.py

    temporal/
      client.py
      workers.py
      activities/
        send_message.py
        llm_tasks.py
        persistence.py
      workflows/
        reminder_workflow.py
        followup_workflow.py
        checkin_workflow.py

    integrations/
      im/
        base.py
        discord.py
        telegram.py
      email/
        base.py
      calendar/
        base.py
      webhook/
        base.py

  observability/
    logging.py
    tracing.py
    metrics.py

  config/
    settings.py

  bootstrap/
    container.py

tests/
  unit/
  integration/
  workflow/
```

---

## 7. 分层职责说明

### 7.1 `domain/`

放真正的业务核心：

- 实体
- 值对象
- 业务规则
- repository 协议

这里不应该依赖：

- FastAPI
- SQLAlchemy
- LiteLLM
- Temporal SDK
- 第三方 IM SDK

---

### 7.2 `application/`

放用例编排：

- 创建提醒
- 关闭提醒
- 处理用户回复
- 写入记忆
- 触发 agent 单轮执行

这里负责协调 `domain` 与 `infrastructure`，但不直接写框架细节。

---

### 7.3 `infrastructure/`

放具体实现：

- DB repository 实现
- Temporal workflow / activity
- LLM provider 实现
- tool runtime 实现
- 外部系统 adapter

---

### 7.4 `api/`

对外 HTTP 接口层：

- 路由
- schema
- 参数校验
- 错误映射

不放业务规则。

---

## 8. 第一阶段核心闭环

### MVP-0：Reminder 闭环

#### 用户故事

用户输入：

> 明天早上 9 点提醒我打卡

系统执行：

1. 识别这是 reminder intent
2. 解析时间
3. 创建 reminder 记录
4. 启动 Temporal workflow
5. 到点调用消息发送 adapter
6. 用户回复“已打卡”
7. workflow 接收 signal
8. reminder 状态关闭

#### 验收标准

- 能持久化 reminder
- 能按时触发
- 能记录发送状态
- 能响应用户回复
- 能关闭 reminder
- 关键链路可追踪

---

## 9. 建议定义的核心接口

### 9.1 `LLMGateway`

```python
class LLMGateway(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...
```

#### 说明

只表达“向模型发起一次结构化请求并得到结果”。

---

### 9.2 `AgentRuntime`

```python
class AgentRuntime(Protocol):
    async def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult: ...
```

#### 说明

只负责“一轮 agent 执行”，不负责长生命周期 workflow。

---

### 9.3 `ToolRuntime`

```python
class ToolRuntime(Protocol):
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

#### 说明

统一工具执行入口。

---

### 9.4 `MessagingAdapter`

```python
class MessagingAdapter(Protocol):
    async def send_message(self, target: MessageTarget, content: OutboundMessage) -> SendResult: ...
```

#### 说明

统一消息发送适配器，不让业务感知 Discord、Telegram、企业 IM 等细节。

---

## 10. 当前明确不做的事

第一阶段暂不做：

- 多 agent 协作图
- 复杂长期记忆检索系统
- 自研 agent DSL
- 微服务化拆分
- 多前端客户端统一体验
- 大而全的权限系统
- 多租户复杂隔离
- 复杂 BI 或运营后台

---

## 11. 关键架构约束

### 约束 1

Route handler 中不得出现业务逻辑。

### 约束 2

`Domain` 层不得依赖 FastAPI、ORM、Temporal、厂商 SDK。

### 约束 3

所有外部模型调用必须经 `llm_gateway`。

### 约束 4

所有工具执行必须经 `tool_runtime`。

### 约束 5

所有外部系统调用必须经 integration adapter。

### 约束 6

Temporal 只允许薄封装，不允许伪通用 workflow facade。

### 约束 7

所有新增功能必须附带测试。

### 约束 8

复杂任务必须先输出 plan，再实施。
