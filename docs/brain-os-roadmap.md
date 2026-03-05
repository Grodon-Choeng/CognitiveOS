# CognitiveOS 重构路线图（第二大脑 / 外脑）

## 0. 新定位与硬约束

### 新定位
本项目定位为个人“外脑”系统，不是传统 Bot 助手。
目标能力：
- 记忆：长期可演进记忆（可写入、检索、压缩、遗忘、追溯）
- 学习：从交互和反馈中持续更新策略
- 决策：提供可执行建议而非只做问答

### 你明确要求（硬约束）
- 保持 `ORM` 不变：`Piccolo`
- 保持 `API 框架` 不变：`Litestar`
- 保持 `依赖注入` 不变：`Dishka`
- 其余模块可重构、可删除
- 历史技术债与兼容包袱可清理
- 历史数据可不保留

## 1. 架构原则（重构后）

- 模块化优先：按能力域拆包，不按“工具类”堆积
- 接口先行：每个域暴露明确 `port`（协议接口）
- 工作流可编排：面向 function calling / agent loop 的显式工具注册
- 可观测性内建：每次认知循环必须有 trace（plan/action/observation/judge）
- 配置中心化：所有模型与 token 策略在 `config.yml` 控制
- 无隐式魔法：避免“猜测式分支”散落在入口层

## 2. 目标目录结构（建议）

```text
app/
  api/                    # Litestar controllers / schemas
  domain/                 # 领域模型与业务规则（纯业务，不依赖框架）
    memory/
    cognition/
    decision/
    learning/
  application/            # 用例编排层（workflow/use-cases）
    commands/
    queries/
    orchestration/
  infrastructure/         # 外部适配器（DB/LLM/Vector/IM/Note/Git/Web）
    persistence/
    llm/
    vector/
    channels/
    note/
  agents/                 # Agent graph + tool registry + policies
  container/              # Dishka providers
  shared/                 # cross-cutting（logging/config/errors/telemetry）
```

说明：
- `services/` 逐步淘汰，能力迁移到 `application + domain + infrastructure`
- `bot/` 与 `channels/` 合并为统一 IM adapter 层
- 以 `tool registry` 作为 function calling 的唯一入口

## 3. 分阶段改造计划

## Phase 1（当前立刻执行）：骨架与边界清理

目标：建立可持续重构骨架，不新增债务。

任务：
- 定义统一 `AgentTool` 协议与 `ToolRegistry`
- 将现有动作（reminder / note / task / memory_search）注册为标准工具
- 统一消息入口：`IM -> Application Command -> Agent`
- 清理入口层中的散落规则（保留少量强规则白名单）
- 统一 trace 事件结构（JSONL + API 可查询）

验收标准：
- 任一新工具接入不需要改 agent 主循环
- message handler 不直接写业务逻辑（只做解析和转发）

## Phase 2：Memory OS（长期记忆主干）

目标：从“能搜”升级为“可演进记忆系统”。

任务：
- 记忆写入策略：重要度、类型、来源、时间衰减
- 检索策略：向量召回 + 元数据过滤 + 评分融合
- 记忆维护任务：压缩、去重、冲突标记、归档
- PromptTemplate 与 MemoryContext 融合策略统一

验收标准：
- 任意回答可追溯到 memory id / source
- 记忆污染率可控（低价值会话不会持续污染长期记忆）

## Phase 3：Decision OS（决策引擎）

目标：输出“建议 + 依据 + 下一步动作”。

任务：
- 增加目标模型（Goal）、约束（Constraint）、计划（Plan）实体
- 设计决策评分（收益/成本/风险/置信度）
- 高价值场景引入多步工具链（检索、外部搜索、文档落地）

验收标准：
- 输出不是单句建议，而是结构化决策结果
- 决策链路可审计

## Phase 4：Learning OS（反馈学习）

目标：系统会“变聪明”而不是只重复。

任务：
- 用户反馈入库（accept/reject/edit）
- 策略更新（提示词版本、工具选择偏好、阈值微调）
- 失败案例自动沉淀为规则候选

验收标准：
- 相同任务场景，后续成功率明显提升

## 4. 允许直接删除/重写的内容

可删原则：
- 不能适配目标架构的临时逻辑
- 重复职责（同一能力在多个 service 实现）
- 隐式耦合（handler 直接操作多个下游）

建议优先整治对象（按风险排序）：
- `app/bot/message_service.py`：业务分支过重，需拆为命令路由
- `app/services/*`：能力聚合过粗，迁移为 application/domain/infrastructure
- 旧模板随机回复路径：统一改为策略化生成

## 5. function calling 最佳实践落地

- 单一工具协议：
  - `name`
  - `description`
  - `input_schema`（JSON Schema）
  - `execute(context, args) -> ToolResult`
- 工具结果统一：
  - `status` (`ok|error|retryable`)
  - `data`
  - `message`
  - `trace`
- Agent 只做编排，不关心工具内部实现细节

## 6. 配置策略（模型与 token）

当前已支持：
- 全局 `llm_max_tokens`
- 节点级 `agent_planner_max_tokens`
- 节点级 `intent_max_tokens`
- 节点级 `memory_judge_max_tokens`

建议：
- 本地模型阶段默认 `null`（不限制）
- 线上化阶段再按节点设置上限

## 7. 本周执行清单（建议）

1. 建立 `ToolRegistry` 与 `AgentTool` 协议（不动 ORM/API/DI）
2. 将 reminder / note / task / memory_search 工具迁移到 registry
3. 将 `message_service` 改为“命令分发 + 统一回复策略”
4. 增加 `agent trace query API` 用于回放诊断
5. 删除不可维护的旧路径（保留最小兼容）

---

本文件作为后续重构基准。后续 PR 需显式标注“对应 Phase/任务/验收标准”。
