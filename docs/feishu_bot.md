# 飞书机器人（长连接模式）

基于飞书官方 SDK 长连接模式的双向交互机器人。

## 功能特性

- 接收飞书用户消息
- 解析提醒命令并创建提醒
- 捕获笔记 / 灵感 / 任务
- 向用户/群聊发送提醒通知

## 配置说明

推荐使用 `config.yml` 配置飞书应用凭证（优先于 `.env` 中的 `IM_CONFIGS`）：

```yaml
im_enabled: true
im_configs:
  - provider: feishu
    enabled: true
    app_id: "cli_xxx"
    app_secret: "xxx"
    verification_token: "xxx"
    encrypt_key: "xxx"
    bypass_proxy: true
```

也可继续使用 `.env` 的 `IM_CONFIGS`：

```env
IM_ENABLED=true
IM_CONFIGS=[
  {
    "provider":"feishu",
    "enabled":true,
    "app_id":"cli_xxx",
    "app_secret":"xxx",
    "bypass_proxy":true,
    "verification_token":"xxx",
    "encrypt_key":"xxx"
  }
]
```

注意事项：

- `app_id` 和 `app_secret` 是长连接模式的必需参数
- `bypass_proxy` 为 `true` 时，会为飞书域名自动设置 `NO_PROXY` 例外（适合本地代理环境）
- `verification_token` 和 `encrypt_key` 需与飞书事件订阅配置一致
- 如果同时配置了 `webhook_url`，仍可用于单向通知 API

## 支持的命令

- `!help` / `/help` - 显示帮助
- `!ping` / `/ping` - 测试连接
- `!remind` - 查看提醒列表
- `!remind <内容>` - 创建提醒

自然语言时间表达式示例：

- `!remind 10分钟后 开会`
- `!remind 明天 10:00 发日报`

## 架构设计

```text
飞书事件（长连接）
  -> app/services/feishu_bot.py
  -> app/bot/feishu_handler.py
  -> app/bot/message_service.py
  -> 提醒/笔记服务
  -> 飞书发送消息 API
```

## 故障排除

### 1. 机器人无法接收消息

- 检查飞书应用是否已订阅 `im.message.receive_v1` 事件权限
- 检查长连接凭证配置（`app_id`、`app_secret`）

### 2. 机器人无法回复消息

- 检查飞书应用是否已获得发送消息权限
- 验证接收者上下文（群聊/用户）是否可达

### 3. 提醒未送达

- 确保服务启动时包含机器人生命周期管理（`app/bot/__init__.py`）
- 检查提醒记录的 `provider` 字段是否为 `feishu`

## 可靠性机制

- 自动重连：指数退避 + 抖动策略
- 消息去重：基于 `message_id` 的 TTL 去重机制
- 错误告警：长连接异常时的限流告警
- 健康状态：通过 `/api/v1/health` 接口暴露 `dependencies.feishu_bot` 状态
