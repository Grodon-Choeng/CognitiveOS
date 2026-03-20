# AGENTS.md：CognitiveOS 仓库智能体协作规范

> 本仓库主要通过 AI coding 方式进行开发。所有在本仓库内工作的智能体，都必须优先保证以下核心目标。
> **不要追求花哨。优先追求：正确、清晰、可持续演进。**

**核心原则：**
- 可维护性
- 架构边界清晰
- 强类型
- 少隐式魔法
- 易测试
- 可增量迭代
- 分层明确

---

## 1. 项目使命

**CognitiveOS** 是一个“个人助理操作系统”。

**系统目标包括：**
- 基于对话创建提醒
- 任务编排
- 等待用户回复后继续执行
- 轻量记忆写入与读取
- 未来扩展到 IM、日历、邮件、Webhook、外部工具系统

⚠️ **第一阶段范围必须保持收敛。**
🎯 **当前首要目标：**把用户请求转化为一个可持久化、可追踪、可暂停、可恢复、可正确完成的工作流。

---

## 2. 已确定的技术决策

以下内容已经拍板，视为仓库级约束，**不允许随意更改**。

- **Web 层**：`FastAPI`
- **Workflow 层**：`Temporal`
- **Tool 协议层**：MCP-compatible 的内部工具契约
- **LLM / 模型提供商访问层**：所有模型调用必须走自有 `llm_gateway`
- **Agent 执行层**：使用自有轻量 `agent_runtime` 抽象（不允许让外部 agent 框架直接成为业务核心）
- **数据层**：`PostgreSQL` + `SQLAlchemy 2.x` + `Alembic`
- **基础工程**：`Python 3.12+`, `uv`, `Pydantic v2`, `pytest`, `ruff`, `mypy`

---

## 3. 第一阶段非目标

除非明确要求，否则**不要**引入以下内容：
- 微服务拆分
- 复杂多智能体图编排
- 自定义 DSL
- 大规模长期记忆检索系统
- 过早设计插件生态
- 不必要的事件总线抽象
- 试验性框架迁移
- “万金油引擎”式通用抽象

📌 **当前形态必须保持为：模块化单体优先**

---

## 4. 分层规则

> ⚠️ 以下规则是强约束。

### 4.1 Domain 层
**包含：**实体（entities）、值对象（value objects）、业务策略（policies）、Repository 协议、Domain errors、必要时的 domain events。
**禁止依赖：**`FastAPI`、SQLAlchemy ORM 模型、Temporal SDK、`LiteLLM`、OpenAI SDK、LangChain、LangGraph、任意厂商 SDK、HTTP 请求/响应对象、任意基础设施实现。
> **要求：**Domain 逻辑必须保持框架无关。

### 4.2 Application 层
**包含：**用例编排、commands、queries、DTOs、协调 domain 与 infrastructure 的边界调用。
**可以依赖：**domain、repository 协议、gateway 协议、adapter 协议。
**禁止包含：**混入 HTTP 细节、混入 ORM 细节、直接调用模型厂商 SDK、手写“替代 Temporal 的流程引擎逻辑”。

### 4.3 API 层
**包含：**route handlers、request/response schemas、依赖注入、HTTP 错误映射。
**禁止包含：**业务规则、直接 ORM 操作、模型调用、tool 执行逻辑、除了调用 application service 之外的 workflow 编排逻辑。
> **要求：**Route handler 必须保持轻薄。

### 4.4 Infrastructure 层
**存放具体实现：**数据库 repository 实现、Temporal workflows / activities、LLM provider 实现、tool runtime 实现、integration adapters、配置与启动 wiring。
> **要求：**所有框架相关、供应商相关代码，都应该放在这一层。

---

## 5. 依赖方向约束

依赖方向必须保持如下：
```text
api -> application -> domain
application -> infrastructure (通过协议/接口)
```
- 允许 infrastructure 实现 application/domain 所需的协议。
- **绝对禁止反向依赖！**

❌ **典型禁止场景：**
- domain 导入 ORM models
- application 导入 FastAPI Request / Response
- route handler 直接导入某厂商 SDK 处理业务逻辑
- domain 导入 Temporal workflow decorator

---

## 6. 仓库结构约定

新增代码时必须遵守现有结构。不要随意增加新的顶层架构目录，除非有充分理由。

```text
.
├── app/
│   ├── api/
│   ├── application/
│   ├── domain/
│   ├── infrastructure/
│   ├── observability/
│   ├── config/
│   └── bootstrap/
└── tests/
    ├── unit/
    ├── integration/
    └── workflow/
```

---

## 7. 外部依赖接入策略

外部依赖是高变化区，必须隔离变化。

**必须包一层的对象：**
LLM providers、agent runtimes、tool execution systems、messaging / email / calendar / webhook providers、其他第三方 API。

**允许的仓库内边界抽象：**
`llm_gateway`, `agent_runtime`, `tool_runtime`, `MessagingAdapter`, `CalendarAdapter`, 其他 integration adapter。

### ⚠️ 重要例外：Temporal
Temporal 是核心平台决策。**禁止为了“可替换”而构建一个假的通用 workflow abstraction 来隐藏 Temporal。**

- **允许的薄封装：**Client 初始化、worker bootstrap、公共 retry policy、workflow 注册辅助、schedule / signal 辅助工具。
- **不允许的封装：**一个把 Temporal 语义抹平的 `WorkflowEngine`、一个伪通用的 pause / resume / signal / trigger 总接口。

**本仓库明确接受 Temporal 的核心概念：**
workflows, activities, signals, queries, updates, timers, retries, durable execution。

---

## 8. LLM 与 Agent 规则

### 8.1 LLM 访问规则
- **所有模型访问必须通过 `llm_gateway`。**
- 业务代码不得直接调用任何 provider SDK。
- 只要发生任何大模型调用，包括 `LLM`、`VLM`、多模态模型或其他推理模型，都必须记录完整调用信息。
- 最少必须记录：原始输入、原始输出、token 使用量、耗时、provider、model、session / conversation / request / trace / chain 信息、调用结果、异常信息，以及所使用密钥的后八位。
- 这些记录默认必须双写到数据库与本地 `jsonl` 文件；两种介质都视为正式记录渠道，后续允许互相导入。
- 这类记录逻辑必须集中在 gateway / runtime / observability 层统一处理，不得散落在业务代码里临时拼接。
- ❌ **禁止：**在 application service 中直接 import OpenAI client；在 HTTP 层混合 prompt 构造与响应整形。

### 8.2 Agent 执行规则
- **所有“单轮 agent 执行”都必须通过 `agent_runtime`。**
- `agent_runtime` **负责**：组装上下文、注入 tool schema、发起模型请求、解释 tool calls、返回结构化结果。
- `agent_runtime` **不负责**：跨时间的长生命周期编排、reminder 生命周期管理、取代 Temporal workflow。
- 📌 **结论：长生命周期执行由 Temporal 负责。**

---

## 9. Tool 协议规则

- 所有工具执行必须通过 `tool_runtime`。
- 工具设计必须保持 **MCP-compatible** 的思想与结构。
- **最少要求：**明确的 name, input schema, output/result 结构；清晰的错误处理；可挂接 logging/tracing；具备 timeout/retry 能力。
- 所有工具调用默认也必须双写到数据库与本地 `jsonl` 文件，至少记录原始输入、原始输出、耗时、超时配置、重试配置、session / conversation / request / trace / chain 信息、错误码与错误信息。
- 不要让模型厂商特定的 tool 格式在代码库内到处传播。必须在工具边界进行统一归一化。

---

## 10. 数据与持久化规则

### 10.1 持久化模型与领域模型分离
- ORM models 不是 domain entities。
- 不要把 ORM model 当成 domain object 在 application 层四处传递。
- **必须**在这些对象之间做清晰转换：ORM persistence model ↔️ domain entities / value objects ↔️ DTOs。

### 10.2 Migration 规则
- 所有 schema 变更必须通过 migration 管理。同步更新 migration 产物。

### 10.3 事务规则
- 事务边界必须清晰。不要把关键写操作藏在不透明的副作用里。

---

## 11. Temporal 工作流规则

> Temporal 是本仓库一等公民。必须直接且清晰地使用它。

- **适用场景**：reminders, follow-up workflows, 等待用户回复后继续, 延迟通知, 跨时间推进的多阶段状态机。
- **工作流规则**：
  - workflow 代码必须保持 deterministic（确定性）。
  - side effects 必须放到 activities。
  - workflow state 必须显式。
  - signal / query / update 命名必须清楚。
  - workflow 的输入、输出、状态假设必须可读。
- 当 workflow 语义发生变化时，必须同步更新文档。

---

## 12. 配置规则

- 配置必须**集中化、类型化**。
- 使用基于环境变量的 settings、显式的 settings models、在安全前提下提供可预测默认值。
- ❌ **禁止在代码库中到处散落 `os.getenv()`。**应通过专门的 settings / bootstrap 模块统一管理。
- Python 依赖缺失时，优先使用 `uv` 补齐与管理依赖。
- PostgreSQL、Temporal 等本地基础设施如果需要本地运行，优先通过仓库内的 `docker compose` 编排文件启动。
- 当前本地编排默认包含 `PostgreSQL`、`Redis`、`Temporal server` 与 `Temporal UI`；变更这些基础设施时，必须同步更新 `compose.yaml` 与 `README.md`。
- Temporal 若依赖动态配置文件，配置文件本身也必须放在仓库内并纳入编排，而不是只依赖容器内默认状态。
- 常用本地开发命令应优先沉淀到 `Makefile`，避免在 README 和协作过程中散落多个不一致的命令版本。
- 应用 settings 默认应支持从项目根目录 `.env` 读取本地配置；若变更读取方式，必须同步更新 `README.md` 与 `.env.example`。
- 新增环境变量、启动方式或基础设施依赖时，必须同步更新 `README.md` 与本文件。

---

## 13. 可观测性规则

> 系统必须可调试。禁止静默失败。

**重要路径至少要具备：**
- structured logging, tracing
- workflow / tool execution logging
- LLM request metadata / integration call logging
- 代码中的日志文本默认使用中文，避免中英文混杂。
- 模型调用留痕属于强约束，不允许只记录摘要而丢失原始输入输出与关键指标。

**捕获异常时：**
- 要么真正处理并记录上下文。
- 要么补充上下文后继续抛出。
- ❌ **绝不吞噬异常。**

---

## 14. 测试规则

所有非平凡改动都**必须**带测试，或更新已有测试。

- **预期测试类型：**`unit tests` (domain), `integration tests` (persistence/adapters), `workflow tests` (Temporal), `API tests` (endpoint)。
- **最低要求：**新业务行为要有 unit 或 integration 覆盖；bug 修复尽量补回归测试。
- ❌ **禁止以“看起来应该能跑”替代验证。**

---

## 15. 类型与代码质量规则

所有非平凡的公开函数、方法，都**必须写类型标注**。

- **要求：**mypy-friendly types；边界处合理使用 Pydantic models；重要函数显式声明返回类型。
- **避免：**大块未类型化 dict、魔法字符串协议、无理由的 `Any`。
- `lint` 和 `typing` 属于完成标准的一部分。
- 代码写完后必须进行格式化；优先使用仓库内既有工具，例如 `ruff check --fix`、`ruff format`，或仓库已采用的其他格式化方式。
- 格式化也属于完成标准的一部分；除非用户明确要求，否则不要跳过。
- 代码中的注释默认使用中文；标识符、目录名、模块名保持英文。
- 在设计类方法时，必须谨慎判断它究竟应该是实例方法、`@staticmethod`、`@classmethod`，还是模块级函数。
- 如果一个函数不依赖实例状态，也不依赖类状态，不要默认写成实例方法。
- 如果它只是语义上归属于某个类命名空间，但不依赖 `self` / `cls`，可以使用 `@staticmethod`。
- 如果它既不依赖实例，也没有强烈的类内聚需求，优先写成模块级函数，避免为了“挂在类上”而增加不必要的方法层级。
- 如果一个方法依赖类级别构造、注册或多态派生逻辑，再考虑 `@classmethod`。
- 对新增或修改的方法，提交前应复查是否真的需要 `self`；在这类判断上宁可保守、显式，也不要偷懒地全部写成实例方法。

---

## 16. 简洁性规则

- **优先选择：**显式代码、小而可组合的函数、直接命名、清晰的数据流。
- **避免：**预判式抽象、“框架套框架”、万物皆基类、不必要的继承层级、没必要的隐藏注册中心。
- 💡 **在很多情况下，少量重复优于过早抽象。**

---

## 17. 变更流程规则

对于任何非平凡任务，智能体必须遵循以下流程：
1. 检查现有文件
2. 总结理解
3. 输出 plan
4. 列出将要修改的文件
5. 做最小正确改动
6. 验证改动
7. 说明假设、风险、后续项

❌ **禁止**在不了解仓库现状的情况下直接大段生成代码。
❌ **禁止**顺手重构无关代码，除非：为了正确性必须修改、用户明确要求、或已清楚说明变更范围。

---

## 18. 仓库智能体输出约定

处理较大任务时，输出通常应包含：
1. 对任务的理解
2. 计划
3. 变更文件列表
4. 实现摘要
5. 验证摘要
6. 假设 / 风险 / 后续事项
*(说明必须具体，不要泛泛而谈)*

---

## 19. 文档更新义务

以下情况发生变化时，**必须更新文档**：
- 架构边界变化
- workflow 语义变化
- config 要求变化
- 外部依赖策略变化
- 目录结构变化
- 核心数据模型假设变化

需同步考虑更新：`README.md`, `docs/architecture.md`, `docs/mvp.md`, `docs/tech-decisions.md`。
- 项目中新增了稳定可复用的协作约束、开发命令、环境依赖或目录约定时，也必须同步更新 `AGENTS.md`。
- 如果 `AGENTS.md` 过大、影响可读性，允许拆分为多个仓库内协作技能文档，例如 `docs/skills/*.md`，并在 `AGENTS.md` 中保留索引与适用范围。

---

## 20. 第一阶段优先级

如果任务存在歧义，**优先实现最小可用的垂直切片**。

当前默认第一条垂直切片：
`reminder creation` ➡️ `persistence` ➡️ `Temporal workflow bootstrap` ➡️ `message sending adapter contract` ➡️ `user reply continuation path`

⚠️ **在这条链路稳定前，不要盲目扩需求面。**

---

## 21. 明确禁止的模式

除非明确要求，**禁止**以下行为：
- 在 FastAPI routes 中写业务逻辑
- 在 application service 中直接调用 provider SDK
- 让 ORM model 逃逸成 domain object
- 给 Temporal 套一层伪通用 workflow facade
- 让 LangChain / LangGraph 深度侵入业务核心
- 为了“灵活”平白增加架构层
- 全部用裸 dict 在各层传来传去
- 搞重度 singleton / service locator
- 随意混用 async / sync
- 在小需求中做大范围仓库重构

---

## 22. 偏好的实现风格

优先编写这样的代码：**明白、强类型、模块化、易审查、方便未来 AI coding session 继续接手。**

> 💡 要假设未来接手的智能体更依赖仓库内清晰度，而不是依赖你此刻的上下文记忆。
> **结论：为连续迭代而写代码，不为新奇感而写代码。**
