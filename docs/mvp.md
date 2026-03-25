# CognitiveOS MVP 范围说明

## 当前目标

第一阶段优先把 assistant 主链路做稳，而不是扩能力面。

当前默认垂直切片是：

```text
reminder creation
-> persistence
-> Temporal workflow bootstrap
-> message sending adapter contract
-> user reply continuation path
```

在这条链路稳定的基础上，conversation 层新增 assistant execution kernel，用来统一 task / reminder / memory / overview 的执行体验。

## P0

P0 目标：把当前会话入口升级成 `state -> plan -> resolve -> execute -> render`

### P0 支持动作

- `show_overview`
- `show_activity`
- `list_tasks`
- `list_reminders`
- `list_memories`
- `create_task`
- `complete_task`
- `cancel_task`
- `create_reminder`
- `cancel_reminder`
- `create_memory`
- `archive_memory`

### P0 支持的引用方式

- 指代词：`这个` / `那个` / `刚才那个`
- 顺序词：`第一个` / `第二个` / `最后一个`
- 关键词：`买药那个提醒`

### P0 验收重点

- 对话入口能统一返回自然回复，而不是每个 service 自己拼一条接口式文案
- 列表回复后，下一轮能解析“第二个”“那个”
- reminder reply continuation 快路径不回退
- 消息审计保留，并带上结构化 turn state
- 当前这些能力已经落地完成

## P1

P1 目标：把“助手感”做出来

- 加强对象解析的稳定性
- 丰富 renderer 的自然语言风格
- 支持 task / reminder 转换动作
- 增加最小澄清与确认机制

### 当前进度

- 已支持 `这个 / 那个 / 刚才那个 / 第一个 / 第二个 / 最后一个 / 另一个`
- 已支持 `convert_task_to_reminder` / `convert_reminder_to_task`
- 已支持最小 confirmation / disambiguation 持久化

## P2

P2 目标：把可用性与恢复能力做扎实

- 执行态持久化（例如 `assistant_turn_states`）
- 失败恢复与重试动作
- 更完整的 conversation behavior tests / resolver tests / renderer tests

### 当前进度

- `assistant_turn_states` 已落地
- failed reminder retry 已落地
- conversation / resolver / renderer / recovery 回归测试已补齐

## 当前非目标

- 不做复杂多智能体图编排
- 不引入长期记忆检索系统
- 不扩更多 IM/外部集成能力
- 不围绕 Temporal 再造一层伪通用 workflow engine

## 当前新增的调试能力

- 已提供 `debug_im` 调试 IM 渠道，用于在飞书长连接被占用时继续验证对话、提醒和续执行闭环
- 已支持通过 HTTP 模拟入站消息、查看最近消息、查看最近会话
- 已支持通过 WebSocket 订阅同一调试会话的实时消息更新
