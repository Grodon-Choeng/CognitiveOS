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

### English

| Expression | Example | Description |
|------------|---------|-------------|
| `X minutes later` | `!remind 5 minutes later submit code` | Remind after X minutes |
| `X hours later` | `!remind 1 hour later meeting` | Remind after X hours |
| `X days later` | `!remind 2 days later review` | Remind after X days |
| `today HH:MM` | `!remind today 18:00 leave work` | Remind at specific time today |
| `tomorrow HH:MM` | `!remind tomorrow 10:00 daily report` | Remind at specific time tomorrow |
| `tomorrow morning` | `!remind tomorrow morning standup` | Remind at 9:00 AM tomorrow |
| `tomorrow afternoon` | `!remind tomorrow afternoon review` | Remind at 2:00 PM tomorrow |
| `before work end` | `!remind before work end submit PR` | Remind at 6:00 PM today |

### 中文

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

### English

```
!remind 5 minutes later submit code
!remind 1 hour later join meeting
!remind today 18:00 leave work
!remind tomorrow 10:00 send daily report
!remind tomorrow morning team standup
!remind before work end submit PR
```

### 中文

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

```env
IM_ENABLED=true
IM_CONFIGS=[{"provider":"discord","bot_token":"YOUR_BOT_TOKEN","command_prefix":"!","enabled":true}]
PROXY_URL=http://127.0.0.1:7897
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
