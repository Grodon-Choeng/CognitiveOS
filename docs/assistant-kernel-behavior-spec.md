# Assistant Kernel 行为规范

## 1. 文档目的

本文档用于定义当前 assistant kernel 在 canonical path 下已经稳定支持的对话行为，并为以下工作提供统一基线：

- 作为 [README.md](/Users/gordon/Code/Personal/CognitiveOS/README.md) 的行为级补充，README 继续只承载高层状态与链路说明。
- 作为 kernel 单元测试与 conversation 回归测试的行为基线，测试应围绕用户可见行为组织，而不是只围绕内部字段组织。
- 作为后续重构的回归标准，任何改变用户可见行为、分流边界或引用解析优先级的改动，都必须先更新本文档再调整实现与测试。

本文档只描述当前代码已经实现、且能从如下模块直接推导出的行为：

- [app/application/conversations/service.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/service.py)
- [app/application/conversations/kernel/facade.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/kernel/facade.py)
- [app/application/conversations/kernel/planner.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/kernel/planner.py)
- [app/application/conversations/kernel/resolver.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/kernel/resolver.py)
- [app/application/conversations/kernel/executor.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/kernel/executor.py)
- [app/application/conversations/kernel/renderer.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/kernel/renderer.py)
- [app/application/reminders/service.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/reminders/service.py)
- [app/application/reminders/conversation_handler.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/reminders/conversation_handler.py)

## 2. 当前行为边界

### 2.1 Canonical kernel path

当前 canonical path 由 `ConversationApplicationService` 驱动，处理顺序固定为：

`resolve context -> reminder fast path -> build turn state -> plan -> execute -> render -> persist`

其中：

- `turn_context` 由 `AssistantTurnContextBuilder` 从 overview、message history、上一轮 assistant state 构建。
- `planner` 先看对话状态 follow-up 规则，再看 referential / natural language 规则，最后才回退到 classifier。
- 对于明显的复杂规则请求，`planner` 会在旧的单动作规则前先做复杂度识别，命中后转入受限的 structured rule plan 预览路径。
- `executor` 对需要对象解析的动作统一走 `ReferenceResolver`。
- `renderer` 负责把执行结果转成用户可见的中文回复。
- 处理完成后，assistant turn state 会通过 state store 或消息审计记录，用于下一轮 follow-up。

### 2.2 Reminder fast path

reminder fast path 是 reminder reply 的过渡兼容 shortcut，不是通用对话理解入口。

- 它只处理“这句话是否像是在回复某条 pending reminder”。
- 它只在极少数高把握场景直接 shortcut 完成。
- 它不能替代 kernel 的 follow-up、引用消解、列表操作、概览、待办、记忆等能力。
- 只要语义不明确、匹配置信不足、或用户像是在改期/拒绝/继续操作，就必须进入确认或回到 kernel。

### 2.3 Legacy adapter 兼容路径

[app/application/conversations/intent_handler.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/intent_handler.py) 中的 `LegacyIntentConversationHandler` 只是兼容旧入口的 adapter：

- 它把旧调用方式转发到 `ConversationKernelFacade`。
- 它不是新增对话能力的主入口。
- 它不应成为行为规范的主要来源。

### 2.4 当前不承诺范围

以下能力不属于当前规范承诺范围：

- 任意自由改写后的同义句都能稳定命中同一行为。
- embedding、RAG、memory augmentation、长期检索式补全理解。
- 把 reminder fast path 当作通用对话理解器。
- 把 legacy adapter 当成主路径继续扩展新能力。
- 对所有“帮我加一个待办...”这类自然表达做稳定承诺。当前稳定承诺的是 `待办：整理周报`、`task: ...` 这类前缀式创建；`帮我加一个待办：整理周报` 依赖 classifier 识别，当前仅部分支持，不作为稳定承诺。

## 3. 对话行为规范

以下规范按“用户说法 -> 系统应该怎么处理”组织。除非特别说明，`message_type` 均为 `text`。

### A. 创建类

#### A1. `明天提醒我买药`

- 输入示例：`明天提醒我买药`
- 前置上下文：无特殊前置要求；canonical kernel path 即可处理。
- 期望计划状态：`ready`
- 期望执行结果：
  - planner 直接命中 `create_reminder`
  - `args.text == "买药"`
  - `args.remind_at` 为解析后的自然时间
  - `args.timezone` 使用默认时区
- 期望渲染风格：
  - 明确说明“已经记成提醒了”
  - 展示时间和提醒内容
  - 保持短句、确认式口吻
- 不应发生的错误行为：
  - 不应进入 fast path
  - 不应要求用户二次确认
  - 不应只返回内部字段而没有自然语言确认

#### A2. `记一下我不想早上八点前被提醒`

- 输入示例：`记一下我不想早上八点前被提醒`
- 前置上下文：无特殊前置要求。
- 期望计划状态：`ready`
- 期望执行结果：
  - planner 直接命中 `create_memory`
  - `args.content == "我不想早上八点前被提醒"`
  - 当前这条精确话术会落成 `memory_type == "note"`
  - 当前只有含 `偏好`、`喜欢`、`不喜欢` 的内容会被规则提升为 `preference`
- 期望渲染风格：
  - 以“记下了”式回复确认写入
  - 当前会按“信息”而不是“偏好”渲染
- 不应发生的错误行为：
  - 不应被当成 reminder create
  - 不应要求 scope object
  - 不应进入确认或歧义态

#### A3. `帮我加一个待办：整理周报`

- 输入示例：`帮我加一个待办：整理周报`
- 前置上下文：无特殊前置要求。
- 当前规范承诺：
  - 不把该自然表达写成稳定承诺。
  - 当前稳定承诺的是前缀式创建，如 `待办：整理周报`。
- 当前部分支持情况：
  - 该话术可能通过 classifier 命中 task create。
  - 但它不是 rules 直达样例，也没有在当前行为基线测试中作为稳定能力收口。
- 不应发生的错误行为：
  - 文档不应把它描述成“系统稳定支持”的 canonical 规则。

### B. Follow-up 引用类

#### B1. `完成第二个`

- 输入示例：`完成第二个`
- 前置上下文：
  - 最近 assistant 展示过待办列表，或 turn state 中有 task 类型的 `visible_candidates`
- 期望计划状态：`ready`
- 期望执行结果：
  - planner 命中 `complete_task`
  - resolver 按 `visible_candidates` 的序号选择第二项
  - executor 完成对应 task
- 期望渲染风格：
  - 明确说明“已经帮你完成这个待办了”
  - 带上被完成的待办标题
- 不应发生的错误行为：
  - 不应从 working set 里重新猜第二项
  - 不应忽略列表上下文去完成 focused reminder

#### B2. `取消刚才那个`

- 输入示例：`取消刚才那个`
- 前置上下文：
  - 当前 turn state 有 reminder 类型的 `focused_object`
- 期望计划状态：`ready`
- 期望执行结果：
  - planner 命中 `cancel_reminder`
  - resolver 对 `刚才那个/这个` 优先命中同类型 `focused_object`
  - executor 取消对应 reminder
- 期望渲染风格：
  - 明确说明该提醒已取消
  - 带上提醒内容
- 不应发生的错误行为：
  - 不应优先取消 `visible_candidates` 里的其他项
  - 不应在高置信 pronoun 情况下进入歧义

#### B3. `不是这个，是另一个`

- 输入示例：`不是这个，是另一个`
- 前置上下文：
  - 上一轮 assistant 处于 disambiguation 场景
  - `visible_candidates` 已存在
  - `last_assistant_action` 指向待继续执行的动作
- 期望计划状态：`ready`
- 期望执行结果：
  - follow-up rules 把 `另一个` 规范化成 `第二个`
  - planner 沿用上一轮 action
  - resolver 选择第二个候选对象
- 期望渲染风格：
  - 回复应该直接落到新的执行结果
  - 不应再次机械重复同一轮歧义问题
- 不应发生的错误行为：
  - 不应退回 classifier
  - 不应丢失上一轮 action

#### B4. `把这个改成明天下午`

- 输入示例：`把这个改成明天下午`
- 前置上下文：
  - 当前焦点或最近列表对象为 reminder
- 期望计划状态：`ready`
- 期望执行结果：
  - planner 命中 `reschedule_reminder`
  - 如果目标文本能解析成时间，则按改期处理
  - resolver 解析 `这个` 到当前 reminder
- 期望渲染风格：
  - 说明“已经帮你改时间了”
  - 展示新的时间，保留提醒内容
- 不应发生的错误行为：
  - 不应误改成 reminder content update
  - 不应在高置信单对象场景直接进入确认

### C. 确认 / 歧义类

#### C0. 复杂规则请求默认先进入确认预览

- 输入示例：`以后工作日的早上9点55提醒我上班打卡，晚上9点05提醒我下班打卡，然后本周六需要加班，也得提醒我打卡，其他非工作日需要提醒打卡的我会另行通知`
- 前置上下文：无特殊前置要求。
- 期望计划状态：
  - planner 不应把整句直接压成一条 `create_reminder`
  - planner 应先识别为 `rule_with_overrides`
  - planner 应产出 `StructuredRulePlan`
- 期望执行结果：
  - 第一轮只返回 preview，不直接执行业务写入
  - assistant state 进入 `dialogue_mode=confirmation`
  - state 中保存 `pending_complex_plan`
- 期望渲染风格：
  - 使用“我理解成以下动作，请确认”式回复
  - 明确列出规则项、override 和 constraint
- 不应发生的错误行为：
  - 不应直接回复“已经记成提醒了”
  - 不应把“其他非工作日我会另行通知”误建成一条 reminder

#### C0.1 复杂规则确认后拆分执行

- 输入示例：`确认`、`按这个来`
- 前置上下文：
  - 上一轮 assistant 已返回复杂规则 preview
  - turn state 中已有 `pending_complex_plan`
- 当前最小实现的期望执行结果：
  - executor 读取 `pending_complex_plan`
  - 会为 recurring rule 生成真正的 recurring reminders
  - 会为 override 生成可落地的单次 reminders
  - 只把 constraint / preference 写成 memory
- 当前最小实现的非承诺范围：
  - 当前只稳定承诺 `workdays + 固定时分` 的 recurring reminder
  - 当前 override 只稳定承诺结构化单日日期，不承诺通用排班规则

#### C1. 低置信但可猜时进入 `needs_confirmation`

- 输入示例：`取消这个`
- 前置上下文：
  - 存在同类型 `focused_object`
  - 计划动作需要引用解析
  - plan confidence 位于 `[0.60, 0.82)` 区间
- 期望计划状态：`needs_confirmation`
- 期望执行结果：
  - executor 不直接执行业务动作
  - 返回 `AssistantConfirmationResult`
  - assistant state 应进入 `dialogue_mode=confirmation`
- 期望渲染风格：
  - 使用“我理解成...先确认一下”式话术
  - 提示用户回复“是的”或更具体描述
- 不应发生的错误行为：
  - 不应直接取消对象
  - 不应把可猜单对象升级成歧义列表

#### C2. 对象不唯一时进入 `needs_disambiguation`

- 输入示例：`取消买那个`
- 前置上下文：
  - `visible_candidates` 或 working set 中有多个标题都匹配“买”
- 期望计划状态：`needs_disambiguation`
- 期望执行结果：
  - executor 不直接执行业务动作
  - 返回候选列表，最多到 disambiguation 配置上限
  - assistant state 应保存 `visible_candidates`
- 期望渲染风格：
  - 列出序号和标题
  - 引导用户直接说“第一个”或把标题说完整
- 不应发生的错误行为：
  - 不应自动猜测其中一个对象
  - 不应把多候选误降级成 confirmation

### D. Reminder reply 类

#### D1. `收到`

- 输入示例：`收到`
- 前置上下文：
  - reminder fast path 匹配到 pending reminder
  - 语义被归类为 acknowledge
  - matcher 为高置信，且 workflow 已启动
- 期望计划状态：`completed`，由 fast path 直接处理，不进入 kernel 计划器
- 期望执行结果：
  - reminder workflow 记录用户回复
  - reminder 状态改为 `completed`
  - conversation 返回 handled result
- 期望渲染风格：
  - 简短确认“这条提醒已收到”
- 不应发生的错误行为：
  - 低置信命中时不应自动完成
  - 普通闲聊不应借 high-confidence relation 被误当成 `收到`

#### D2. `改成明天`

- 输入示例：`改成明天`
- 前置上下文：
  - fast path 能匹配到 reminder
- 期望计划状态：`needs_confirmation`，由 fast path 返回
- 期望执行结果：
  - reminder 不自动完成
  - workflow 不记录“已收到”
  - 返回一段提示，要求用户继续把改期说完整
- 期望渲染风格：
  - 明确说明“先不记为完成”
  - 提示“可以直接继续说改这条到明天下午”
- 不应发生的错误行为：
  - 不应直接把 reminder 标记成 completed
  - 不应直接启动 reschedule 动作

#### D3. `不是这个`

- 输入示例：`不是这个`
- 前置上下文：
  - fast path 能匹配到 reminder
- 期望计划状态：`pass_to_kernel`
- 期望执行结果：
  - fast path 不消费这条消息
  - 由 kernel 接手后续 follow-up / disambiguation 行为
  - reminder 状态保持 `pending`
- 期望渲染风格：
  - 由 kernel 决定；fast path 不应提前生成“已收到”类回复
- 不应发生的错误行为：
  - 不应自动完成 reminder
  - 不应把拒绝类文本强行解释为 acknowledge

#### D4. 普通闲聊消息

- 输入示例：`今天天气不错`
- 前置上下文：
  - 即使消息关系能高置信命中某条 reminder，也不代表它是 reminder reply
- 期望计划状态：`pass_to_kernel`
- 期望执行结果：
  - fast path 先按语义归类为 `pass_to_kernel`
  - 不消费 reminder，不改状态，不记录 workflow reply
- 期望渲染风格：
  - 由 kernel 或 fallback 决定；fast path 不应生成 reminder handling 文案
- 不应发生的错误行为：
  - 不应因为 `parent_message_id`/thread relation 命中而 shortcut 完成

### E. 复杂规则请求类

#### E1. 复杂规则默认进入 preview，不直接执行

- 复杂规则请求命中 `StructuredRulePlan` 后，第一轮只返回 preview。
- assistant turn state 必须进入 `dialogue_mode=confirmation`。
- `pending_complex_plan` 必须保存在 assistant turn state，供下一轮确认恢复。

#### E2. 确认后拆成多动作执行

- 第二轮用户回复 `确认`、`按这个来`、`就这么建` 时，真实 conversation 入口应优先从 turn state 恢复 `pending_complex_plan`。
- 当前最小闭环会把 recurring rule 创建为 recurring reminders，把 override 创建为 one-off reminders，再把 constraint 写入 memory。
- 不允许依赖测试手工注入 confirmation context 才能执行。

#### E3. 约束性表达进入 constraint / memory，而不是 reminder

- 诸如“其他非工作日我会另行通知”这类表达，应进入 constraint memory / preference。
- 这类约束不能被误拆成新的 reminder，也不能塞回 recurring reminder 的正文。

#### E4. 当前 recurring 支持范围与非承诺范围

- 当前稳定承诺的 recurring 范围：`工作日 + 固定时分`，并保留 timezone。
- 当前稳定承诺的 override 范围：结构化单日日期，如 `本周六`，会落成 one-off reminders。
- 当前不承诺：任意 RRULE、节假日推导、复杂排班、跨规则冲突求解、对 recurring reminder 的完整 reply continuation 语义。

## 4. 解析优先级规范

引用解析由 [app/application/conversations/kernel/resolver.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/kernel/resolver.py) 定义。当前优先级不是一个抽象策略声明，而是现有代码行为：

1. `focused_object`
2. `visible_candidates`
3. ordinal reference
4. pronoun / keyword reference
5. working set fallback
6. ambiguity / unsupported fallback

### 4.1 `focused_object` 优先于 `visible_candidates`

当用户说 `这个`、`那个`、`刚才那个` 这类指代，且当前 turn state 中存在同类型 `focused_object` 时：

- resolver 先命中 `focused_object`
- 即使 `visible_candidates` 中也有列表对象，也不覆盖当前焦点

示例：

- 当前焦点是“刚刚讨论的提醒”
- 最近列表里有“列表里的第一个提醒”和“列表里的第二个提醒”
- 用户说 `取消这个`
- 结果应优先取消“刚刚讨论的提醒”

### 4.2 序号引用只对 `visible_candidates` 生效

`第一个`、`第二个`、`第三个`、`最后一个`、`倒数第二个`、`上一个` 的当前规则如下：

- 优先从 `visible_candidates` 取序号位置
- 不把 working set 当作列表序号的替代来源
- `上一个/前一个` 还要求当前焦点存在，且当前焦点出现在 `visible_candidates` 中

示例：

- 用户说 `第二个`
- `visible_candidates` 的第二项是 `r-visible-2`
- working set 的第二项是 `r-working-2`
- 结果必须落到 `r-visible-2`

示例：

- 用户说 `最后一个`
- 没有 `visible_candidates`
- 即使 working set 里有 pending reminders
- 当前实现也不承诺“最后一个”回退到 working set，结果应为 unsupported

### 4.3 关键词引用

像 `买药那个提醒` 这类关键词引用：

- 先在 `visible_candidates` 中模糊匹配标题
- 若 `visible_candidates` 不足，再退到同类型 working set
- 命中一个对象时执行 confirmation policy
- 命中多个对象时进入 `needs_disambiguation`

### 4.4 无显式引用词但动作需要对象

当 plan 没有 `reference_text`，但动作需要对象时：

- 若当前焦点存在且类型匹配，优先用 `focused_object`
- 否则退到同类型 working set 首项
- 若是 failed reminder 且候选超过一个，优先进入歧义
- 最终是否直接执行、进入确认或进入歧义，受 confidence policy 控制

### 4.5 Confirmation policy

当前阈值来自 [app/application/conversations/kernel/policies.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/kernel/policies.py)：

- `confidence >= 0.82`：自动执行
- `0.60 <= confidence < 0.82`：`needs_confirmation`
- `confidence < 0.60`：当前实现会把单候选降为歧义处理

## 5. Fast Path 规范

reminder fast path 的行为由 [app/application/reminders/service.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/reminders/service.py) 决定。

### 5.1 允许 shortcut 的条件

只有同时满足以下条件时，fast path 才允许直接 shortcut：

- 文本语义被 `_classify_reminder_reply_semantics` 判定为 `acknowledge`
- matcher 命中 pending reminder
- matcher 置信度为 `high`
- reminder 已经有 `workflow_id`

当前典型示例：`收到`

### 5.2 不允许 shortcut 的条件

以下情况不允许直接 shortcut：

- 语义不是 acknowledge
- 文本包含列表/概览/待办/记忆等 pass-to-kernel 关键词
- 文本体现改期/延期，如 `改成明天`
- 文本体现拒绝或不相关，如 `不是这个`
- matcher 置信度低
- reminder workflow 尚未启动

### 5.3 什么时候必须回到 kernel

返回 `pass_to_kernel` 的典型场景：

- 普通闲聊消息
- 拒绝类 follow-up，需要 kernel 继续理解
- workflow 未启动
- 文本本身就应由 kernel 处理的其他能力

### 5.4 什么时候必须进入确认

返回 `needs_confirmation` 的典型场景：

- reminder match 低置信
- 语义像是改期/延期，但 fast path 不负责直接执行改期

此时 fast path 可以返回提示文本与最小 assistant state，但不能把 reminder 自动完成。

## 6. 行为测试映射

| 规范条目 | 测试文件 | 测试名 | 是否已覆盖 | 备注 |
| --- | --- | --- | --- | --- |
| C0 复杂规则请求先进入预览确认 | [tests/unit/test_complex_rule_requests.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_complex_rule_requests.py) | `test_复杂规则请求不会被压成一条_reminder`、`test_复杂规则请求默认进入_confirmation_preview` | 已覆盖 | 验证不会误压成单条 reminder，且默认返回 preview |
| C0.1 复杂规则确认后拆分执行 | [tests/unit/test_complex_rule_requests.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_complex_rule_requests.py) | `test_确认后会拆成多个动作执行`、`test_其他非工作日我另行通知_不会被误建成_reminder_文本` | 已覆盖 | 当前会创建 recurring reminders、one-off overrides 与 constraint memory |
| E2 preview -> confirm -> execute 真实入口闭环 | [tests/unit/test_complex_rule_requests.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_complex_rule_requests.py) | `test_真实_conversation_service_能恢复_pending_complex_plan并完成确认执行` | 已覆盖 | 验证 preview 后保存 pending plan，确认时经 `ConversationApplicationService` 自动恢复并执行 |
| A1 明天提醒我买药 -> create_reminder | [tests/unit/test_kernel_followup_behaviors.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_followup_behaviors.py) | `test_明天提醒我买药_创建提醒并返回自然确认` | 已覆盖 | 断言 plan、执行调用与渲染 |
| A2 记一下我不想早上八点前被提醒 -> create_memory | [tests/unit/test_kernel_followup_behaviors.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_followup_behaviors.py) | `test_记一下我不想早上八点前被提醒_写入记忆并自然回复` | 已覆盖 | 当前按 `note` 收口，不把该精确话术承诺为 preference typing |
| A3 帮我加一个待办：整理周报 | 无稳定承诺测试 | 无 | 缺失但不补 | 当前仅部分支持，不列为稳定承诺 |
| A3 替代稳定承诺：前缀式 task create | [app/application/conversations/intent_handler.py](/Users/gordon/Code/Personal/CognitiveOS/app/application/conversations/intent_handler.py) | 依赖 classifier / prefixed content | 部分支持 | 当前未在本映射表收口为用户话术基线 |
| B1 完成第二个 | [tests/unit/test_kernel_followup_behaviors.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_followup_behaviors.py) | `test_完成第二个_会完成第二条待办` | 已覆盖 | 断言完成第二条 task |
| B2 取消刚才那个 | [tests/unit/test_kernel_followup_behaviors.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_followup_behaviors.py) | `test_取消刚才那个_会取消聚焦提醒` | 已覆盖 | 验证 focused object 优先 |
| B3 不是这个，是另一个 | [tests/unit/test_kernel_followup_behaviors.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_followup_behaviors.py) | `test_不是这个_是另一个_仍然走_followup_规则` | 已覆盖 | 验证 follow-up action 继承与 reference 归一化 |
| B4 把这个改成明天下午 | [tests/unit/test_kernel_followup_behaviors.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_followup_behaviors.py) | `test_改成明天下午_生成_reminder_改期计划` | 已覆盖 | 验证改期 plan、执行与渲染 |
| C1 低置信但可猜 -> needs_confirmation | [tests/unit/test_kernel_confirmation_and_disambiguation.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_confirmation_and_disambiguation.py) | `test_当置信不足但可猜时_进入_needs_confirmation` | 已覆盖 | 验证 confirmation result |
| C1 低置信 pronoun -> confirmation | [tests/unit/test_kernel_confirmation_and_disambiguation.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_confirmation_and_disambiguation.py) | `test_取消这个_低置信时进入_confirmation_而不是直接取消` | 已覆盖 | 验证 pronoun 分流与确认渲染 |
| C2 多对象匹配 -> needs_disambiguation | [tests/unit/test_kernel_confirmation_and_disambiguation.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_confirmation_and_disambiguation.py) | `test_当对象不唯一时_进入_needs_disambiguation` | 已覆盖 | 验证多候选不自动执行 |
| 解析优先级：focused object 优先于 visible candidates | [tests/unit/test_kernel_reference_resolution.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_reference_resolution.py) | `test_focused_object_与_visible_candidates_冲突时_这个优先命中_focused_object` | 已覆盖 | 验证 pronoun 优先级 |
| 解析优先级：第二个命中 visible candidates | [tests/unit/test_kernel_reference_resolution.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_reference_resolution.py) | `test_完成第三个_命中最近候选列表中的第三项`、`test_第二个_只从_visible_candidates_取序号而不从_working_set_猜测` | 已覆盖 | 验证 ordinal 不回退猜 working set |
| 解析优先级：最后一个不回退到 working set | [tests/unit/test_kernel_reference_resolution.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_kernel_reference_resolution.py) | `test_没有最近候选列表时_最后一个不回退到_working_set_猜测` | 已覆盖 | 验证 unsupported 边界 |
| 解析优先级：关键词引用 | [tests/unit/test_conversation_kernel_resolver.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_conversation_kernel_resolver.py) | `test_reference_resolver_supports_keyword_hint` | 已覆盖 | 不在四个目标文件中，但属于现有行为基线 |
| D1 收到 -> fast path completed | [tests/unit/test_reminder_fast_path_safety.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_reminder_fast_path_safety.py) | `test_收到_高置信提醒回复可以直接_completed` | 已覆盖 | 验证 completed shortcut |
| D2 改成明天 -> needs_confirmation | [tests/unit/test_reminder_fast_path_safety.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_reminder_fast_path_safety.py) | `test_改成明天_不会把提醒直接标记_completed` | 已覆盖 | 验证不自动完成 |
| D3 不是这个 -> pass_to_kernel | [tests/unit/test_reminder_fast_path_safety.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_reminder_fast_path_safety.py) | `test_不是这个_不会把提醒直接标记_completed` | 已覆盖 | 验证拒绝类回 kernel |
| D4 普通闲聊 -> pass_to_kernel | [tests/unit/test_reminder_fast_path_safety.py](/Users/gordon/Code/Personal/CognitiveOS/tests/unit/test_reminder_fast_path_safety.py) | `test_同一聊天里的普通消息不会误命中最近_reminder`、`test_普通闲聊即使有高置信关联也仍然_pass_to_kernel` | 已覆盖 | 分别验证低关联和高关联下都不 shortcut |

## 维护规则

- 每新增一个用户可见 conversation 行为，必须同步更新本文档。
- 每条稳定行为规范至少对应一条自然话术测试。
- README 只保留高层状态与链路，不承载全部行为细节。
- 如果 canonical path、fast path 边界、或 resolver 优先级发生变化，必须先更新本文档，再修改实现与测试。
- 只有已经被代码与测试收口的行为，才能写进“当前稳定承诺”；未收口能力只能写成“当前仅部分支持”或“当前不承诺”。
