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
   ├── Retrieval Service    # 关联检索
   ├── Reflection Service   # 反思总结
   └── Reminder Service     # 提醒系统
   ↓
Memory Layer
   ├── Raw Markdown         # 原始记录
   ├── Structured Markdown  # 结构化笔记
   ├── Embedding Index      # 语义索引 (FAISS)
   └── Metadata DB          # 元数据 (SQLite)
   ↓
LLM Layer
   ├── Basic Extraction     # 基础提取
   ├── Contextual Reasoning # 上下文推理
   └── Reflective Thinking  # 反思思考
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

### 5. 提醒系统

- metadata 中存 `due_date`
- cron 任务扫描
- 推送到 IM

LLM 只负责理解意图，规则引擎负责执行。

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
```

Markdown 是展示层，不是唯一真相。

## 演进路径

### 阶段 1：确定性系统 ✅ (已完成)

- [x] Raw 保存
- [x] JSON 结构化
- [x] Markdown 输出

### 阶段 2：记忆增强

- [ ] embedding 生成
- [ ] FAISS 向量索引
- [ ] RAG 检索模式

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
| LLM | OpenAI / GLM / Qwen | 认知计算 |
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
│   │   └── knowledge_item.py      # 知识项模型
│   ├── repositories/
│   │   └── knowledge_item_repo.py # 知识项仓储
│   ├── routes/
│   │   ├── health.py              # 健康检查
│   │   ├── im.py                  # IM 测试路由
│   │   ├── items.py               # 知识项路由
│   │   └── webhook.py             # Webhook 路由
│   ├── schemas/
│   │   └── webhook.py             # 请求/响应 DTO
│   ├── services/
│   │   ├── capture_service.py     # 自动记录
│   │   ├── notification_service.py # IM 通知
│   │   ├── structuring_service.py # 结构化输出
│   │   ├── retrieval_service.py   # 关联检索 (TODO)
│   │   ├── reflection_service.py  # 反思总结 (TODO)
│   │   └── reminder_service.py    # 提醒系统 (TODO)
│   └── utils/
│       ├── jsons.py               # JSON 工具
│       ├── logging.py             # 日志系统
│       └── times.py               # 工具函数
├── storage/
│   ├── raw/                       # 原始 Markdown
│   └── structured/                # 结构化 Markdown
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

### 配置 IM 通知（可选）

支持以下 IM 平台：

| 平台 | Provider | 安全机制 |
|------|----------|---------|
| 企业微信 | `wecom` | 无签名 |
| 钉钉 | `dingtalk` | 签名校验 |
| 飞书 | `feishu` | 签名校验 |
| Discord | `discord` | 无签名 |

**企业微信配置：**
```bash
IM_ENABLED=true
IM_PROVIDER=wecom
IM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
```

**钉钉配置（推荐，支持签名）：**
```bash
IM_ENABLED=true
IM_PROVIDER=dingtalk
IM_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
IM_SECRET=SECxxx  # 加签密钥
```

**飞书配置：**
```bash
IM_ENABLED=true
IM_PROVIDER=feishu
IM_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_HOOK
IM_SECRET=your_secret  # 可选
```

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

### POST /webhook

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
curl -X POST http://127.0.0.1:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"content": "今天学到了一个新概念", "source": "telegram"}'
```

### GET /items

获取最近的知识项列表

**响应**:
```json
[
  {
    "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3",
    "raw_text": "今天学到了一个新概念...",
    "source": "telegram",
    "tags": [],
    "created_at": "2026-02-19T06:00:00+00:00"
  }
]
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

## 设计决策

### 为什么不用 LangChain / LangGraph？

初期不需要 Agent 框架，原因：
- 不可控
- 难调试
- 结果不可重复
- 容易污染知识库

这是知识系统，不是聊天机器人。

### 为什么需要向量库？

LLM 没有"长期自我体系"。向量库把过往思想作为可检索语义记忆，这才叫"结合已有体系"，否则每次都是重新思考。

### 为什么 Markdown 不是唯一真相？

Markdown 是展示层。真正的知识需要：
- 结构化数据
- 向量索引
- 元数据管理
- 版本控制

## 当前状态

项目处于 **阶段 1：确定性系统** 的初期实现。

已完成：
- Webhook 接收
- Raw Markdown 保存
- SQLite 元数据存储

下一步：
- 完善结构化输出
- 集成 LLM 进行半自动整理
- 添加向量索引支持

---

> "你不是在做笔记工具，你是在做一个可计算的认知外脑。"
