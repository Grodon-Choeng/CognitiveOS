# CognitiveOS

[English](README_EN.md) | 简体中文

一个可进化的个人认知操作系统，用于构建可计算的认知外脑。

## 设计理念

这不是一个笔记工具，而是一个：

- **可检索** - 通过向量索引实现语义搜索
- **可推理** - 结合已有知识体系进行关联思考
- **可反思** - 周期性总结与主题发现
- **可进化** - 从确定性系统逐步演进到自主代理

核心原则：**规则控制流程，LLM 只负责认知计算。**

## 系统架构

```
IM Layer
   ↓
Gateway Layer（Webhook / Auth / Routing）
   ↓
Core Service Layer（规则优先）
   ├── Capture Service      # 自动记录
   ├── Structuring Service  # 半自动整理
   ├── Retrieval Service    # 关联检索 (RAG)
   ├── Prompt Service       # 提示词管理
   ├── Notification Service # IM 通知
   ├── Reflection Service   # 反思总结 (TODO)
   └── Reminder Service     # 提醒系统
   ↓
Memory Layer
   ├── Raw Markdown         # 原始记录
   ├── Structured Markdown  # 结构化笔记
   ├── Embedding Index      # 语义索引 (FAISS)
   └── Metadata DB          # 元数据 (SQLite)
   ↓
LLM Layer (LiteLLM 统一接口)
   ├── OpenAI / Azure       # 国际模型
   ├── Qwen / GLM / DeepSeek # 国产模型
   └── Embedding            # 向量化
```

## 核心能力模块

### 1. 自动记录（确定性）

```
IM → Raw 保存 → 返回确认
```

- 不调用 LLM
- 永远可追溯
- 永远可回滚

这是底层安全网，确保所有输入都被完整保存。

### 2. 半自动整理（结构化）

触发条件：
- 长文本
- 包含特殊标记（如 `#整理`）

```
Raw → LLM 输出 JSON → Markdown Builder → 双链生成
```

### 3. 关联思考（RAG 模式）

```
新输入 → embedding → FAISS 检索 top-k → 构造 context prompt → LLM 分析
```

把过往思想作为可检索语义记忆，实现"结合已有体系"的思考。

### 4. 反思层

周期性自动：
- 发现相似主题
- 发现重复观点
- 发现未完成问题
- 生成周总结

### 5. 提醒系统 ✅

通过 Discord Bot 设置提醒，支持自然语言时间表达式：

```
!remind 5分钟后 提交代码
!remind 明天 10:00 发日报
!remind 下班前 提交PR
```

后台任务每 30 秒扫描待发送提醒，到时自动推送。

详见 [docs/reminder.md](docs/reminder.md)

### 6. Discord / 飞书 Bot ✅

双向交互模式，支持：
- 接收消息并处理
- 设置提醒
- 知识捕获

详见 [docs/discord_bot.md](docs/discord_bot.md)
和 [docs/feishu_bot.md](docs/feishu_bot.md)

## 数据结构

```python
class KnowledgeItem:
    id: str
    raw_text: str           # 原始文本
    structured_text: str    # 结构化文本
    tags: list[str]         # 标签
    links: list[str]        # 双链
    embedding: vector       # 向量
    created_at: datetime
    updated_at: datetime

class Prompt:
    name: str               # 提示词名称
    description: str        # 描述
    content: str            # 提示词内容
    category: str           # 分类
```

Markdown 是展示层，不是唯一真相。

## 演进路径

### 阶段 1：确定性系统 ✅ (已完成)

- [x] Raw 保存
- [x] JSON 结构化
- [x] Markdown 输出

### 阶段 2：记忆增强 ✅ (已完成)

- [x] embedding 生成 (LiteLLM)
- [x] FAISS 向量索引
- [x] RAG 检索模式
- [x] 提示词数据库存储

### 阶段 3：认知增强

- [ ] 自动发现主题聚类
- [ ] 自动生成索引页
- [ ] 周期性总结

### 阶段 4：自主代理

- [ ] 多步骤推理
- [ ] 自动扩展图谱
- [ ] 自动提出问题

## 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| 核心控制 | Python | 服务层逻辑 |
| Web 框架 | Litestar | API 服务 |
| 依赖注入 | Dishka | 服务解耦 |
| ORM | Piccolo + SQLite | 元数据存储 |
| 缓存 | Cashews + Redis | 数据缓存 |
| 向量索引 | FAISS | 语义记忆 |
| LLM 接口 | LiteLLM | 统一调用 OpenAI/Qwen/GLM/DeepSeek |
| 展示层 | Markdown | 知识呈现 |
| 版本控制 | Git | 历史追溯 |
| 定时任务 | Cron | 提醒系统 |

## 项目结构

```
CognitiveOS/
├── app/
│   ├── __init__.py
│   ├── config.py                  # 配置管理
│   ├── container.py               # 依赖注入容器
│   ├── main.py                    # 应用入口
│   ├── core/
│   │   ├── __init__.py
│   │   ├── exceptions.py          # 异常定义
│   │   ├── model.py               # 基础模型 (BaseModel, TimestampMixin)
│   │   └── repository.py          # 基础仓储 (BaseRepository)
│   ├── im/                        # IM 适配器
│   │   ├── __init__.py
│   │   ├── base.py                # 基础接口
│   │   ├── wecom.py               # 企业微信
│   │   ├── dingtalk.py            # 钉钉
│   │   ├── feishu.py              # 飞书
│   │   └── discord.py             # Discord
│   ├── models/
│   │   ├── knowledge_item.py      # 知识项模型
│   │   ├── prompt.py              # 提示词模型
│   │   └── sessions.py            # 会话模型
│   ├── repositories/
│   │   ├── knowledge_item_repo.py # 知识项仓储
│   │   └── prompt_repo.py         # 提示词仓储
│   ├── routes/
│   │   ├── health.py              # 健康检查
│   │   ├── im.py                  # IM 测试路由
│   │   ├── items.py               # 知识项路由
│   │   ├── prompts.py             # 提示词管理路由
│   │   ├── retrieval.py           # RAG 检索路由
│   │   └── webhook.py             # Webhook 路由
│   ├── schemas/
│   │   ├── im.py                  # IM 响应 DTO
│   │   ├── prompt.py              # 提示词 DTO
│   │   ├── retrieval.py           # 检索 DTO
│   │   └── webhook.py             # Webhook DTO
│   ├── services/
│   │   ├── capture_service.py     # 自动记录
│   │   ├── embedding_service.py   # Embedding 生成
│   │   ├── knowledge_item_service.py # 知识项服务
│   │   ├── llm_service.py         # LLM 统一接口 (LiteLLM)
│   │   ├── notification_service.py # IM 通知
│   │   ├── prompt_service.py      # 提示词服务
│   │   ├── retrieval_service.py   # RAG 检索
│   │   ├── structuring_service.py # 结构化输出
│   │   ├── vector_store.py        # FAISS 向量存储
│   │   ├── reflection_service.py  # 反思总结 (TODO)
│   │   └── reminder_service.py    # 提醒系统
│   └── utils/
│       ├── jsons.py               # JSON 工具
│       ├── logging.py             # 日志系统
│       └── times.py               # 工具函数
├── storage/
│   ├── raw/                       # 原始 Markdown
│   ├── structured/                # 结构化 Markdown
│   └── vectors/                   # FAISS 索引
├── piccolo_conf.py                # 数据库配置
├── piccolo_migrations/            # 迁移文件
├── pyproject.toml                 # 项目依赖
└── cognitive.db                   # SQLite 数据库
```

## 快速开始

### 安装依赖

```bash
uv sync
```

### 启动 Docker 服务（可选）

```bash
# 启动 Redis 缓存
docker-compose up -d

# 查看服务状态
docker-compose ps
```

### 数据库迁移

```bash
uv run piccolo migrations new cognitive --auto
uv run piccolo migrations forwards cognitive
```

### 启动服务

```bash
uv run uvicorn app.main:app --reload
```

服务将在 http://127.0.0.1:8000 启动。

### 配置 LLM

使用 LiteLLM 统一接口，切换模型只需修改配置：

```bash
# OpenAI
LLM_MODEL=openai/gpt-4o-mini
LLM_API_KEY=sk-xxx
EMBEDDING_MODEL=openai/text-embedding-3-small

# 通义千问
LLM_MODEL=qwen/qwen-turbo
LLM_API_KEY=sk-xxx
EMBEDDING_MODEL=qwen/text-embedding-v3

# 智谱 GLM
LLM_MODEL=zhipu/glm-4-flash
LLM_API_KEY=xxx
EMBEDDING_MODEL=zhipu/embedding-3

# DeepSeek
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=sk-xxx
```

### 配置 IM 通知（可选）

支持以下 IM 平台：

| 平台 | Provider | Webhook 模式 | Bot 长连接模式 |
|------|----------|-------------|---------------|
| 企业微信 | `wecom` | ✅ 无签名 | ❌ |
| 钉钉 | `dingtalk` | ✅ 签名校验 | ❌ 规划中 |
| 飞书 | `feishu` | ✅ 签名校验 | ✅ SDK 长连接 |
| Discord | `discord` | ✅ 无签名 | ✅ Bot API |

**企业微信配置（Webhook 模式）：**
```bash
IM_ENABLED=true
IM_PROVIDER=wecom
IM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
```

**钉钉配置（Webhook 模式，支持签名）：**
```bash
IM_ENABLED=true
IM_PROVIDER=dingtalk
IM_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
IM_SECRET=SECxxx  # 加签密钥
```

**飞书配置（Bot 长连接模式，推荐）：**
```bash
IM_ENABLED=true
IM_CONFIGS=[{"provider":"feishu","app_id":"cli_xxx","app_secret":"xxx","enabled":true}]
```

**飞书配置（Webhook 模式）：**
```bash
IM_ENABLED=true
IM_CONFIGS=[{"provider":"feishu","webhook_url":"https://open.feishu.cn/open-apis/bot/v2/hook/xxx","secret":"xxx","enabled":true}]
```

详见 [docs/feishu_bot.md](docs/feishu_bot.md)

### 常用命令 (Makefile)

```bash
make dev      # 启动开发服务器
make up       # 启动 Docker 服务
make down     # 停止 Docker 服务
make migrate  # 运行数据库迁移
make lint     # 代码检查
make clean    # 清理缓存文件
```

## API 接口

### POST /api/v1/webhook

捕获笔记（自动记录）

**请求体** (`CaptureRequest`):
```json
{
  "content": "今天学到了一个新概念",
  "source": "telegram"
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| content | string | 是 | - | 笔记内容 |
| source | string | 否 | "im" | 来源标识 |

**响应** (`CaptureResponse`):
```json
{
  "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3"
}
```

**示例**:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{"content": "今天学到了一个新概念", "source": "telegram"}'
```

### GET /items

游标分页获取知识项列表

**查询参数**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| limit | int | 否 | 20 | 每页数量，最大 100 |
| cursor | string | 否 | null | 游标（上一页返回的 next_cursor） |
| sort_field | string | 否 | "created_at" | 排序字段：created_at / updated_at |
| sort_order | string | 否 | "desc" | 排序方向：asc / desc |

**响应**:
```json
{
  "items": [
    {
      "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3",
      "raw_text": "今天学到了一个新概念...",
      "source": "telegram",
      "tags": [],
      "created_at": "2026-02-19T06:00:00+00:00"
    }
  ],
  "next_cursor": "63996705-da46-4bad-ac58-236de1f1abf1",
  "has_more": true
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| items | array | 知识项列表 |
| next_cursor | string | 下一页游标，无更多数据时为 null |
| has_more | bool | 是否还有更多数据 |

**示例**:
```bash
# 第一页
curl "http://127.0.0.1:8000/items?limit=10"

# 下一页（使用返回的 next_cursor）
curl "http://127.0.0.1:8000/items?limit=10&cursor=63996705-da46-4bad-ac58-236de1f1abf1"

# 按更新时间升序
curl "http://127.0.0.1:8000/items?sort_field=updated_at&sort_order=asc"
```

### GET /items/{item_uuid}

获取单个知识项详情

**响应**:
```json
{
  "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3",
  "raw_text": "今天学到了一个新概念",
  "structured_text": null,
  "source": "telegram",
  "tags": [],
  "links": [],
  "created_at": "2026-02-19T06:00:00+00:00",
  "updated_at": "2026-02-19T06:00:00+00:00"
}
```

### POST /items/{item_uuid}/structure

生成结构化 Markdown 文件

**响应**:
```json
{
  "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3",
  "title": "今天学到了一个新概念",
  "file_path": "storage/structured/10-xxx.md"
}
```

### POST /search

语义搜索知识库

**请求体**:
```json
{
  "query": "学习笔记",
  "top_k": 5
}
```

**响应**:
```json
[
  {
    "item": { "uuid": "xxx", "raw_text": "...", ... },
    "distance": 0.123
  }
]
```

### POST /rag

RAG 问答

**请求体**:
```json
{
  "query": "我学过什么关于 Python 的内容？",
  "top_k": 5
}
```

**响应**:
```json
{
  "query": "我学过什么关于 Python 的内容？",
  "answer": "根据你的知识库...",
  "sources": [...]
}
```

### POST /index/{item_uuid}

为单个知识项生成向量索引

### POST /index/rebuild

重建全部向量索引

### 提示词管理 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/prompts` | GET | 列出所有提示词 |
| `/prompts/{name}` | GET | 获取单个提示词 |
| `/prompts` | POST | 创建提示词 |
| `/prompts/{name}` | PUT | 更新提示词 |
| `/prompts/{name}` | DELETE | 删除提示词 |

**更新提示词示例**:
```bash
curl -X PUT http://127.0.0.1:8000/prompts/rag_system \
  -H "Content-Type: application/json" \
  -d '{"content": "新的提示词内容...", "description": "更新描述"}'
```

## 设计决策

### 为什么用 LiteLLM？

统一接口调用所有 LLM，切换模型只需修改配置：
- 支持 OpenAI、Qwen、GLM、DeepSeek 等 100+ 模型
- 统一的 embedding 接口
- 无需修改代码

### 为什么不用 LangChain / LangGraph？

初期不需要 Agent 框架，原因：
- 不可控
- 难调试
- 结果不可重复
- 容易污染知识库

这是知识系统，不是聊天机器人。

### 为什么提示词存数据库？

- 修改提示词无需重启服务
- 可通过 API 动态调整
- 支持版本追溯

### 为什么需要向量库？

LLM 没有"长期自我体系"。向量库把过往思想作为可检索语义记忆，这才叫"结合已有体系"，否则每次都是重新思考。

### 为什么 Markdown 不是唯一真相？

Markdown 是展示层。真正的知识需要：
- 结构化数据
- 向量索引
- 元数据管理
- 版本控制

## 当前状态

项目处于 **阶段 2：记忆增强** 已完成，**提醒系统** 已完成。

已完成：
- Webhook 接收
- Raw Markdown 保存
- SQLite 元数据存储
- IM 多平台适配（企业微信/钉钉/飞书/Discord）
- LiteLLM 统一接口
- Embedding 生成
- FAISS 向量索引
- RAG 检索模式
- 提示词数据库存储
- Discord Bot 双向交互
- 飞书 Bot 双向交互（长连接）
- 提醒系统（自然语言时间表达式）

下一步：
- 自动发现主题聚类
- 自动生成索引页
- 周期性总结

---

> "你不是在做笔记工具，你是在做一个可计算的认知外脑。"
