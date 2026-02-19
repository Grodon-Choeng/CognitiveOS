# CognitiveOS

English | [简体中文](README.md)

An evolvable Personal Cognitive Operating System for building a computable cognitive external brain.

## Design Philosophy

This is not a note-taking tool, but a system that is:

- **Searchable** - Semantic search via vector indexing
- **Reasonable** - Associative thinking combined with existing knowledge
- **Reflective** - Periodic summarization and theme discovery
- **Evolvable** - Progressive evolution from deterministic system to autonomous agent

Core Principle: **Rules control the flow, LLM only handles cognitive computation.**

## System Architecture

```
IM Layer
   ↓
Gateway Layer (Webhook / Auth / Routing)
   ↓
Core Service Layer (Rule-first)
   ├── Capture Service      # Auto capture
   ├── Structuring Service  # Semi-auto structuring
   ├── Retrieval Service    # Associative retrieval
   ├── Reflection Service   # Reflective summarization
   └── Reminder Service     # Reminder system
   ↓
Memory Layer
   ├── Raw Markdown         # Raw records
   ├── Structured Markdown  # Structured notes
   ├── Embedding Index      # Semantic index (FAISS)
   └── Metadata DB          # Metadata (SQLite)
   ↓
LLM Layer
   ├── Basic Extraction     # Basic extraction
   ├── Contextual Reasoning # Contextual reasoning
   └── Reflective Thinking  # Reflective thinking
```

## Core Capability Modules

### 1. Auto Capture (Deterministic)

```
IM → Raw Save → Return Confirmation
```

- No LLM calls
- Always traceable
- Always rollbackable

This is the underlying safety net ensuring all inputs are completely preserved.

### 2. Semi-auto Structuring

Triggers:
- Long text
- Special markers (e.g., `#structure`)

```
Raw → LLM outputs JSON → Markdown Builder → Bidirectional link generation
```

### 3. Associative Thinking (RAG Mode)

```
New input → embedding → FAISS retrieve top-k → Construct context prompt → LLM analysis
```

Uses past thoughts as searchable semantic memory for "combining existing system" thinking.

### 4. Reflection Layer

Periodic automation:
- Discover similar themes
- Discover repeated viewpoints
- Discover unresolved questions
- Generate weekly summaries

### 5. Reminder System

- Store `due_date` in metadata
- Cron job scanning
- Push to IM

LLM only handles intent understanding, rule engine handles execution.

## Data Structure

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
```

Markdown is the presentation layer, not the single source of truth.

## Evolution Path

### Phase 1: Deterministic System ✅ (Completed)

- [x] Raw save
- [x] JSON structuring
- [x] Markdown output

### Phase 2: Memory Enhancement

- [ ] Embedding generation
- [ ] FAISS vector index
- [ ] RAG retrieval mode

### Phase 3: Cognitive Enhancement

- [ ] Auto-discover theme clustering
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
| LLM | OpenAI / GLM / Qwen | Cognitive computation |
| Presentation | Markdown | Knowledge presentation |
| Version Control | Git | History tracing |
| Scheduler | Cron | Reminder system |

## Project Structure

```
CognitiveOS/
├── app/
│   ├── __init__.py
│   ├── config.py                  # Configuration
│   ├── container.py               # DI container
│   ├── main.py                    # Application entry
│   ├── core/
│   │   ├── __init__.py
│   │   ├── model.py               # Base models
│   │   └── repository.py          # Base repository
│   ├── models/
│   │   └── knowledge_item.py      # Knowledge item model
│   ├── repositories/
│   │   └── knowledge_item_repo.py # Knowledge item repository
│   ├── routes/
│   │   ├── health.py              # Health check
│   │   ├── items.py               # Knowledge item routes
│   │   └── webhook.py             # Webhook route
│   ├── schemas/
│   │   └── webhook.py             # Request/Response DTOs
│   ├── services/
│   │   ├── capture_service.py     # Auto capture
│   │   ├── structuring_service.py # Structured output
│   │   ├── retrieval_service.py   # Associative retrieval (TODO)
│   │   ├── reflection_service.py  # Reflection (TODO)
│   │   └── reminder_service.py    # Reminder system (TODO)
│   └── utils/
│       ├── logging.py             # Logging system
│       └── times.py               # Utility functions
├── storage/
│   ├── raw/                       # Raw Markdown
│   └── structured/                # Structured Markdown
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

### POST /webhook

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
curl -X POST http://127.0.0.1:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"content": "Learned a new concept today", "source": "telegram"}'
```

### GET /items

Get recent knowledge items list

**Response**:
```json
[
  {
    "uuid": "e238a58f-3d25-49fb-b80b-f8c0e33b76f3",
    "raw_text": "Learned a new concept today...",
    "source": "telegram",
    "tags": [],
    "created_at": "2026-02-19T06:00:00+00:00"
  }
]
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
  "file_path": "storage/structured/10-learned-a-new-concept-today.md"
}
```

## Design Decisions

### Why not LangChain / LangGraph?

No need for Agent framework in early stage:
- Uncontrollable
- Hard to debug
- Non-reproducible results
- Easy to pollute knowledge base

This is a knowledge system, not a chatbot.

### Why vector database?

LLM has no "long-term self-system". Vector database makes past thoughts searchable semantic memory, enabling "combining existing system" thinking. Otherwise, every thought starts from scratch.

### Why is Markdown not the single source of truth?

Markdown is the presentation layer. True knowledge requires:
- Structured data
- Vector indexing
- Metadata management
- Version control

## Current Status

Project is at **Phase 1: Deterministic System** initial implementation.

Completed:
- Webhook receiving
- Raw Markdown saving
- SQLite metadata storage
- UUID-based API
- Dual-layer caching

Next steps:
- Refine structured output
- Integrate LLM for semi-auto structuring
- Add vector index support

---

> "You're not building a note-taking tool, you're building a computable cognitive external brain."
