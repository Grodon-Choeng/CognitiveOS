# Discord Bot

A bidirectional Discord Bot that enables interactive communication with CognitiveOS.

一个支持与 CognitiveOS 双向交互的 Discord Bot。

## Features / 功能

| Feature | Description |
|---------|-------------|
| Receive Messages | Bot listens to messages in channels and DMs |
| Send Notifications | Push notifications via webhook |
| Set Reminders | Create reminders with natural language |
| Knowledge Capture | Capture notes to knowledge base |
| Auto Reconnect | Exponential backoff with jitter |
| Message Deduplication | TTL-based deduplication |
| Alert Throttling | Cooldown mechanism for alerts |
| Health Monitoring | Status exposed via API |

| 功能 | 说明 |
|------|------|
| 接收消息 | Bot 监听频道和私信中的消息 |
| 发送通知 | 通过 webhook 推送通知 |
| 设置提醒 | 使用自然语言创建提醒 |
| 知识捕获 | 捕获笔记到知识库 |
| 自动重连 | 指数退避 + 抖动策略 |
| 消息去重 | 基于 TTL 的去重机制 |
| 告警限流 | 冷却时间机制 |
| 健康监控 | 通过 API 暴露状态 |

## Setup / 配置

### 1. Create Discord Bot / 创建 Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click `New Application` → Enter name → `Create`
3. Left menu `Bot` → `Add Bot`
4. Copy the **Token**
5. Enable **Privileged Gateway Intents**:
   - ✅ Message Content Intent
   - ✅ Server Members Intent (optional)

1. 访问 [Discord Developer Portal](https://discord.com/developers/applications)
2. 点击 `New Application` → 输入名称 → `Create`
3. 左侧菜单 `Bot` → `Add Bot`
4. 复制 **Token**
5. 启用 **Privileged Gateway Intents**:
   - ✅ Message Content Intent
   - ✅ Server Members Intent (可选)

### 2. Invite Bot to Server / 邀请 Bot 到服务器

1. Left menu `OAuth2` → `URL Generator`
2. Scopes: Check `bot`
3. Bot Permissions: Check `Send Messages`, `Read Message History`, `View Channels`
4. Copy the generated URL, open in browser, invite to server

1. 左侧菜单 `OAuth2` → `URL Generator`
2. Scopes: 勾选 `bot`
3. Bot Permissions: 勾选 `Send Messages`, `Read Message History`, `View Channels`
4. 复制生成的 URL，在浏览器中打开，邀请到服务器

### 3. Configuration / 配置

```env
# .env
IM_ENABLED=true
IM_CONFIGS=[{"provider":"discord","bot_token":"YOUR_BOT_TOKEN","command_prefix":"!","enabled":true}]
PROXY_URL=http://127.0.0.1:7897
```

**Note**: `PROXY_URL` is required in China mainland for Discord connection.

**注意**: 中国大陆需要配置 `PROXY_URL` 才能连接 Discord。

## Commands / 命令

| Command | Description |
|---------|-------------|
| `!help` | Show help message |
| `!ping` | Test bot connection |
| `!remind` | List my reminders |
| `!remind <content>` | Create a reminder |
| `灵感 <content>` | Capture an idea |
| `任务 <content>` | Capture a task |
| `记录 <content>` | Capture a note |

| 命令 | 说明 |
|------|------|
| `!help` | 显示帮助 |
| `!ping` | 测试连接 |
| `!remind` | 查看提醒列表 |
| `!remind <内容>` | 创建提醒 |
| `灵感 <内容>` | 记录灵感 |
| `任务 <内容>` | 记录任务 |
| `记录 <内容>` | 记录笔记 |

## Architecture / 架构

```
app/
├── bot/
│   ├── __init__.py
│   ├── discord_handler.py   # Message handling / 消息处理
│   └── message_service.py   # Shared message service / 共享消息服务
├── services/
│   ├── discord_bot.py       # Bot core / Bot 核心
│   ├── reminder_service.py  # Reminder service / 提醒服务
│   └── reminder_checker.py  # Background checker / 后台检查
└── models/
    └── reminder.py          # Reminder model / 提醒模型
```

## How It Works / 工作原理

```
User Message → Discord Gateway → Bot Event Handler → MessageService → Response
                ↓
         (Proxy if needed)
```

1. Bot connects to Discord Gateway via WebSocket
2. Receives message events
3. Parses commands and content
4. Calls corresponding service
5. Sends response back to channel/user

1. Bot 通过 WebSocket 连接到 Discord Gateway
2. 接收消息事件
3. 解析命令和内容
4. 调用对应服务
5. 发送响应回频道/用户

## Reliability Mechanisms / 可靠性机制

### Auto Reconnect / 自动重连

```python
@staticmethod
def _next_backoff(attempt: int) -> float:
    exp = min(attempt, 6)
    return min(60.0, (2**exp) + random.uniform(0, 1.5))
```

- Exponential backoff with jitter / 指数退避 + 抖动策略
- Max wait: 60 seconds / 最大等待: 60 秒
- Auto reconnect loop / 自动重连循环

### Message Deduplication / 消息去重

```python
def _is_duplicate(self, message_id: int, ttl_seconds: int = 600) -> bool:
    # TTL-based deduplication / 基于 TTL 的去重
```

- Prevent duplicate message processing / 防止重复处理
- TTL: 600 seconds / TTL: 600 秒
- Auto cleanup when cache > 2000 / 缓存超过 2000 条自动清理

### Alert Throttling / 告警限流

```python
async def _alert(self, key: str, message: str, cooldown_seconds: int = 300) -> None:
    # 5-minute cooldown for same alert type / 同类型告警 5 分钟冷却
```

- Cooldown: 300 seconds / 冷却时间: 300 秒
- Prevent alert storm / 防止告警风暴

### Health Monitoring / 健康监控

`GET /api/v1/health` returns bot status:

```json
{
  "discord_bot": {
    "enabled": true,
    "running": true,
    "connected": true,
    "reconnect_attempts": 0,
    "guild_count": 1,
    "last_connected_at": "2026-02-20T...",
    "last_event_at": "2026-02-20T...",
    "last_error_at": null,
    "last_error": null
  }
}
```

## Troubleshooting / 故障排除

### Bot not responding / Bot 无响应

1. Check if `PROXY_URL` is configured (required in China)
2. Check if `Message Content Intent` is enabled in Discord Developer Portal
3. Check logs for connection errors
4. Check `/api/v1/health` for bot status

1. 检查是否配置了 `PROXY_URL`（中国大陆必需）
2. 检查 Discord Developer Portal 中是否启用了 `Message Content Intent`
3. 查看日志中的连接错误
4. 检查 `/api/v1/health` 查看 Bot 状态

### Connection timeout / 连接超时

```log
# If you see this, proxy is not working
INFO - discord.client - logging in using static token
# (stuck here)
```

Solution: Verify proxy URL and ensure proxy service is running.

解决方案: 验证代理 URL 并确保代理服务正在运行。

### Frequent reconnects / 频繁重连

```log
WARNING - Discord Bot disconnected from Discord (attempt=5)
WARNING - Discord Bot disconnected, retry in 32.5s (attempt=5)
```

Possible causes:
- Unstable proxy connection / 代理连接不稳定
- Network issues / 网络问题
- Discord API rate limiting / Discord API 限流

可能原因:
- 代理连接不稳定
- 网络问题
- Discord API 限流

## Related Docs / 相关文档

- [Reminder Feature](reminder.md) - Detailed reminder documentation / 详细提醒文档
- [Feishu Bot](feishu_bot.md) - Feishu bot documentation / 飞书机器人文档
