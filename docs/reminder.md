# Reminder Feature / 提醒功能

A flexible reminder system that allows you to set reminders through Discord bot with natural language time expressions.

一个灵活的提醒系统，支持通过 Discord Bot 使用自然语言时间表达式设置提醒。

## Commands / 命令

| Command | Description |
|---------|-------------|
| `!help` | Show help message / 显示帮助 |
| `!remind` | List my reminders / 查看我的提醒列表 |
| `!remind <content>` | Create a reminder / 创建提醒 |

| 命令 | 说明 |
|------|------|
| `!help` | 显示帮助 |
| `!remind` | 查看我的提醒列表 |
| `!remind <内容>` | 创建提醒 |

## Time Expressions / 时间表达式

**Note**: Currently only Chinese time expressions are supported. English expressions are planned for future updates.

**注意**: 当前仅支持中文时间表达式，英文表达式计划在未来版本中支持。

### 中文时间表达式

| 表达式 | 示例 | 说明 |
|--------|------|------|
| `X分钟后` | `!remind 5分钟后 提交代码` | X分钟后提醒 |
| `X小时后` | `!remind 1小时后 开会` | X小时后提醒 |
| `X天后` | `!remind 2天后 代码审查` | X天后提醒 |
| `今天 HH:MM` | `!remind 今天 18:00 下班` | 今天指定时间提醒 |
| `明天 HH:MM` | `!remind 明天 10:00 发日报` | 明天指定时间提醒 |
| `明天早上` | `!remind 明天早上 晨会` | 明天早上9点提醒 |
| `明天下午` | `!remind 明天下午 代码审查` | 明天下午2点提醒 |
| `下班前` / `今天下班前` | `!remind 下班前 提交PR` | 今天18点提醒 |

## Examples / 示例

```
!remind 5分钟后 提交代码
!remind 1小时后 开会
!remind 今天 18:00 下班
!remind 明天 10:00 发日报
!remind 明天早上 晨会
!remind 下班前 提交PR
```

## Architecture / 架构

```
app/
├── models/
│   └── reminder.py          # Reminder data model / Reminder 数据模型
├── services/
│   ├── reminder_service.py  # Reminder service (parse time, CRUD) / 提醒服务（解析时间、CRUD）
│   └── reminder_checker.py  # Background task (check every 30s) / 后台任务（每30秒检查）
└── bot/
    └── discord_handler.py   # Discord command handler / Discord 命令处理
```

## Configuration / 配置

### Discord Bot Setup / Discord Bot 配置

```yaml
im_enabled: true
im_configs:
  - provider: discord
    enabled: true
    bot_token: "YOUR_BOT_TOKEN"
    command_prefix: "!"
    heartbeat_timeout: 120
```

### Database Migration / 数据库迁移

```bash
uv run piccolo migrations new cognitive --auto
uv run piccolo migrations forwards cognitive
```

## How It Works / 工作原理

1. **Create Reminder / 创建提醒**: User sends `!remind` command via Discord
2. **Parse Time / 解析时间**: System parses natural language time expression
3. **Store / 存储**: Reminder is saved to database
4. **Check / 检查**: Background task checks pending reminders every 30 seconds
5. **Notify / 通知**: When time arrives, bot sends notification to the user/channel

1. **创建提醒**: 用户通过 Discord 发送 `!remind` 命令
2. **解析时间**: 系统解析自然语言时间表达式
3. **存储**: 提醒保存到数据库
4. **检查**: 后台任务每30秒检查待发送的提醒
5. **通知**: 时间到达时，Bot 向用户/频道发送通知
