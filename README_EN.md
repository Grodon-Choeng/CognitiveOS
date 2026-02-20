# CognitiveOS

English | [简体中文](README.md)

An evolvable personal cognitive operating system for building a computable cognitive external brain.

## Design Philosophy

This is not a note-taking tool, but a:

- **Searchable** - Semantic search via vector indexing
- **Reasonable** - Associative thinking based on existing knowledge
- **Reflective** - Periodic summarization and topic discovery
- **Evolvable** - Gradually evolving from deterministic systems to autonomous agents

Core Principle: **Rules control the flow, LLM only handles cognitive computation.**

## System Architecture

```
IM Layer
   ↓
Gateway Layer (Webhook / Auth / Routing)
   ↓
Core Service Layer (Rule-First)
   ├── Capture Service      # Auto capture
   ├── Structuring Service  # Semi-auto structuring
   ├── Retrieval Service    # Associative retrieval (RAG)
   ├── Prompt Service       # Prompt management
   ├── Notification Service # IM notification
   ├── Reflection Service   # Reflection (TODO)
   └── Reminder Service     # Reminder system (TODO)
   ↓
Memory Layer
   ├── Raw Markdown         # Raw records
   ├── Structured Markdown  # Structured notes
   ├── Embedding Index      # Semantic index (FAISS)
   └── Metadata DB          # Metadata (SQLite)
   ↓
LLM Layer (LiteLLM Unified Interface)
   ├── OpenAI / Azure       # International models
   ├── Qwen / GLM / DeepSeek # Chinese models
   └── Embedding            # Vectorization
```

## Core Capability Modules

### 1. Auto Capture (Deterministic)

```
IM → Raw save → Return confirmation
```

- No LLM calls
- Always traceable
- Always rollbackable

This is the safety net ensuring all inputs are completely preserved.

### 2. Semi-auto Structuring

Triggers:
- Long text
- Contains special markers (e.g., `#整理`)

```
Raw → LLM outputs JSON → Markdown Builder → Bidirectional link generation
```

### 3. Associative Thinking (RAG Mode)

```
New input → embedding → FAISS retrieve top-k → Construct context prompt → LLM analysis
```

Using past thoughts as searchable semantic memory to achieve "thinking based on existing system".

### 4. Reflection Layer

Periodic automatic:
- Discover similar topics
- Discover repeated viewpoints
- Discover unresolved questions
- Generate weekly summaries

### 5. Reminder System ✅

Set reminders via Discord Bot with natural language time expressions:

```
!remind 5 minutes later submit code
!remind tomorrow 10:00 send daily report
!remind before work end submit PR
```

Background task scans pending reminders every 30 seconds and auto-pushes when due.

See [docs/reminder.md](docs/reminder.md)

### 6. Discord / Feishu Bot ✅

Bidirectional interaction mode, supports:
- Receive and process messages
- Set reminders
- Knowledge capture

See [docs/discord_bot.md](docs/discord_bot.md)
and [docs/feishu_bot.md](docs/feishu_bot.md)

## Data Structures

```python
class KnowledgeItem:
    id: str
    raw_text: str           # Raw text
    structured_text: str    # Structured text
    tags: list[str]         # Tags
    links: list[str]        # Bidirectional links
    embedding: vector       # Vector
    created_at: datetime
    updated_at: datetime

class Prompt:
    name: str               # Prompt name
    description: str        # Description
    content: str            # Prompt content
    category: str           # Category
```

Markdown is presentation layer, not the single source of truth.

## Evolution Path

### Phase 1: Deterministic System ✅ (Completed)

- [x] Raw save
- [x] JSON structuring
- [x] Markdown output

### Phase 2: Memory Enhancement ✅ (Completed)

- [x] Embedding generation (LiteLLM)
- [x] FAISS vector index
- [x] RAG retrieval mode
- [x] Prompt database storage

### Phase 3: Cognitive Enhancement

- [ ] Auto-discover topic clustering
- [ ] Auto-generate index pages
- [ ] Periodic summarization

### Phase 4: Autonomous Agent

- [ ] Multi-step reasoning
- [ ] Auto-expand knowledge graph
- [ ] Auto-raise questions

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Core Control | Python | Service layer logic |
| Web Framework | Litestar | API service |
| DI | Dishka | Service decoupling |
| ORM | Piccolo + SQLite | Metadata storage |
| Cache | Cashews + Redis | Data caching |
| Vector Index | FAISS | Semantic memory |
| LLM Interface | LiteLLM | Unified call to OpenAI/Qwen/GLM/DeepSeek |
| Presentation | Markdown | Knowledge presentation |
| Version Control | Git | History tracing |
| Scheduling | Cron | Reminder system |

## Project Structure

```
CognitiveOS/
├── app/
│   ├── __init__.py
│   ├── config.py                  # Configuration management
│   ├── container.py               # DI container
│   ├── main.py                    # Application entry
│   ├── core/
│   │   ├── __init__.py
│   │   ├── exceptions.py          # Exception definitions
│   │   ├── model.py               # Base models
│   │   └── repository.py          # Base repository
│   ├── im/                        # IM adapters
│   │   ├── __init__.py
│   │   ├── base.py                # Base interface
│   │   ├── wecom.py               # WeCom
│   │   ├── dingtalk.py            # DingTalk
│   │   ├── feishu.py              # Feishu
│   │   └── discord.py             # Discord
│   ├── models/
│   │   ├── knowledge_item.py      # Knowledge item model
│   │   ├── prompt.py              # Prompt model
│   │   └── sessions.py            # Session model
│   ├── repositories/
│   │   ├── knowledge_item_repo.py # Knowledge item repository
│   │   └── prompt_repo.py         # Prompt repository
│   ├── routes/
│   │   ├── health.py              # Health check
│   │   ├── im.py                  # IM test routes
│   │   ├── items.py               # Knowledge item routes
│   │   ├── prompts.py             # Prompt management routes
│   │   ├── retrieval.py           # RAG retrieval routes
│   │   └── webhook.py             # Webhook route
│   ├── schemas/
│   │   ├── im.py                  # IM response DTOs
│   │   ├── prompt.py              # Prompt DTOs
│   │   ├── retrieval.py           # Retrieval DTOs
│   │   └── webhook.py             # Webhook DTOs
│   ├── services/
│   │   ├── capture_service.py     # Auto capture
│   │   ├── embedding_service.py   # Embedding generation
│   │   ├── knowledge_item_service.py # Knowledge item service
│   │   ├── llm_service.py         # LLM unified interface (LiteLLM)
│   │   ├── notification_service.py # IM notification
│   │   ├── prompt_service.py      # Prompt service
│   │   ├── retrieval_service.py   # RAG retrieval
│   │   ├── structuring_service.py # Structured output
│   │   ├── vector_store.py        # FAISS vector store
│   │   ├── reflection_service.py  # Reflection (TODO)
│   │   └── reminder_service.py    # Reminder system (TODO)
│   └── utils/
│       ├── jsons.py               # JSON utilities
│       ├── logging.py             # Logging system
│       └── times.py               # Utility functions
├── storage/
│   ├── raw/                       # Raw Markdown
│   ├── structured/                # Structured Markdown
│   └── vectors/                   # FAISS index
├── piccolo_conf.py                # Database config
├── piccolo_migrations/            # Migration files
├── pyproject.toml                 # Dependencies
└── cognitive.db                   # SQLite database
```

## Quick Start

### Install Dependencies

```bash
uv sync
```

### Start Docker Services (Optional)

```bash
# Start Redis cache
docker-compose up -d

# Check service status
docker-compose ps
```

### Database Migration

```bash
uv run piccolo migrations new cognitive --auto
uv run piccolo migrations forwards cognitive
```

### Start Service

```bash
uv run uvicorn app.main:app --reload
```

Service will start at http://127.0.0.1:8000.

### Configure LLM

Using LiteLLM unified interface, switch models by changing config:

```bash
# OpenAI
LLM_MODEL=openai/gpt-4o-mini
LLM_API_KEY=sk-xxx
EMBEDDING_MODEL=openai/text-embedding-3-small

# Qwen
LLM_MODEL=qwen/qwen-turbo
LLM_API_KEY=sk-xxx
EMBEDDING_MODEL=qwen/text-embedding-v3

# Zhipu GLM
LLM_MODEL=zhipu/glm-4-flash
LLM_API_KEY=xxx
EMBEDDING_MODEL=zhipu/embedding-3

# DeepSeek
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=sk-xxx
```

### Configure IM Notifications (Optional)

Supported IM platforms:

| Platform | Provider | Webhook Mode | Bot Long Connection Mode |
|----------|----------|--------------|--------------------------|
| WeCom | `wecom` | ✅ No signature | ❌ |
| DingTalk | `dingtalk` | ✅ Signature verification | ✅ Stream mode |
| Feishu | `feishu` | ✅ Signature verification | ✅ SDK long connection |
| Discord | `discord` | ✅ No signature | ✅ Bot API |

**WeCom configuration (Webhook mode):**
```bash
IM_ENABLED=true
IM_PROVIDER=wecom
IM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
```

**DingTalk configuration (Webhook mode, with signature):**
```bash
IM_ENABLED=true
IM_PROVIDER=dingtalk
IM_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
IM_SECRET=SECxxx  # Signing secret
```

**Feishu configuration (Bot long connection mode, recommended):**
```bash
IM_ENABLED=true
IM_CONFIGS=[{"provider":"feishu","app_id":"cli_xxx","app_secret":"xxx","enabled":true}]
```

**Feishu configuration (Webhook mode):**
```bash
IM_ENABLED=true
IM_CONFIGS=[{"provider":"feishu","webhook_url":"https://open.feishu.cn/open-apis/bot/v2/hook/xxx","secret":"xxx","enabled":true}]
```

See [docs/feishu_bot.md](docs/feishu_bot.md) for details.

### Common Commands (Makefile)

```bash
make dev      # Start development server
make up       # Start Docker services
make down     # Stop Docker services
make migrate  # Run database migrations
make lint     # Code linting
make clean    # Clean cache files
```

## API Reference

### POST /api/v1/webhook

Capture note (auto record)

**Request Body** (`CaptureRequest`):
```json
{
  "content": "Learned a new concept today",
  "source": "telegram"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| content | string | Yes | - | Note content |
| source | string | No | "im" | Source identifier |

**Response** (`CaptureResponse`):
```json
{
  "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3"
}
```

**Example**:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{"content": "Learned a new concept today", "source": "telegram"}'
```

### GET /items

Cursor paginated knowledge items list

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| limit | int | No | 20 | Items per page, max 100 |
| cursor | string | No | null | Cursor (next_cursor from previous page) |
| sort_field | string | No | "created_at" | Sort field: created_at / updated_at |
| sort_order | string | No | "desc" | Sort order: asc / desc |

**Response**:
```json
{
  "items": [
    {
      "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3",
      "raw_text": "Learned a new concept today...",
      "source": "telegram",
      "tags": [],
      "created_at": "2026-02-19T06:00:00+00:00"
    }
  ],
  "next_cursor": "63996705-da46-4bad-ac58-236de1f1abf1",
  "has_more": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| items | array | Knowledge items list |
| next_cursor | string | Next page cursor, null when no more data |
| has_more | bool | Whether more data exists |

**Examples**:
```bash
# First page
curl "http://127.0.0.1:8000/items?limit=10"

# Next page (use returned next_cursor)
curl "http://127.0.0.1:8000/items?limit=10&cursor=63996705-da46-4bad-ac58-236de1f1abf1"

# Sort by updated_at ascending
curl "http://127.0.0.1:8000/items?sort_field=updated_at&sort_order=asc"
```

### GET /items/{item_uuid}

Get single knowledge item details

**Response**:
```json
{
  "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3",
  "raw_text": "Learned a new concept today",
  "structured_text": null,
  "source": "telegram",
  "tags": [],
  "links": [],
  "created_at": "2026-02-19T06:00:00+00:00",
  "updated_at": "2026-02-19T06:00:00+00:00"
}
```

### POST /items/{item_uuid}/structure

Generate structured Markdown file

**Response**:
```json
{
  "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3",
  "title": "Learned a new concept today",
  "file_path": "storage/structured/10-xxx.md"
}
```

### POST /search

Semantic search knowledge base

**Request Body**:
```json
{
  "query": "study notes",
  "top_k": 5
}
```

**Response**:
```json
[
  {
    "item": { "uuid": "xxx", "raw_text": "...", ... },
    "distance": 0.123
  }
]
```

### POST /rag

RAG Q&A

**Request Body**:
```json
{
  "query": "What have I learned about Python?",
  "top_k": 5
}
```

**Response**:
```json
{
  "query": "What have I learned about Python?",
  "answer": "Based on your knowledge base...",
  "sources": [...]
}
```

### POST /index/{item_uuid}

Generate vector index for single knowledge item

### POST /index/rebuild

Rebuild all vector indexes

### Prompt Management API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/prompts` | GET | List all prompts |
| `/prompts/{name}` | GET | Get single prompt |
| `/prompts` | POST | Create prompt |
| `/prompts/{name}` | PUT | Update prompt |
| `/prompts/{name}` | DELETE | Delete prompt |

**Update prompt example**:
```bash
curl -X PUT http://127.0.0.1:8000/prompts/rag_system \
  -H "Content-Type: application/json" \
  -d '{"content": "New prompt content...", "description": "Updated description"}'
```

## Design Decisions

### Why LiteLLM?

Unified interface to call all LLMs, switch models by changing config:
- Supports OpenAI, Qwen, GLM, DeepSeek and 100+ models
- Unified embedding interface
- No code changes needed

### Why not LangChain / LangGraph?

No need for Agent framework in early stage:
- Uncontrollable
- Hard to debug
- Non-reproducible results
- Easy to pollute knowledge base

This is a knowledge system, not a chatbot.

### Why store prompts in database?

- Modify prompts without service restart
- Dynamic adjustment via API
- Version tracing support

### Why vector database?

LLM has no "long-term self-system". Vector database makes past thoughts searchable semantic memory, achieving "thinking based on existing system", otherwise every time is fresh thinking.

### Why Markdown is not the single source of truth?

Markdown is presentation layer. True knowledge needs:
- Structured data
- Vector index
- Metadata management
- Version control

## Current Status

Project is at **Phase 2: Memory Enhancement** completed, **Reminder System** completed.

Completed:
- Webhook receiving
- Raw Markdown saving
- SQLite metadata storage
- IM multi-platform adaptation (WeCom/DingTalk/Feishu/Discord)
- LiteLLM unified interface
- Embedding generation
- FAISS vector index
- RAG retrieval mode
- Prompt database storage
- Discord Bot bidirectional interaction
- Feishu Bot bidirectional interaction (long connection)
- Reminder system (natural language time expressions)

Next steps:
- Auto-discover topic clustering
- Auto-generate index pages
- Periodic summarization

---

> "You're not building a note-taking tool, you're building a computable cognitive external brain."
