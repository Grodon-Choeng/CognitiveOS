.PHONY: dev prod up down logs clean migrate test lint help

help:
	@echo "CognitiveOS - Makefile Commands"
	@echo ""
	@echo "Development:"
	@echo "  make dev        Start development server"
	@echo "  make up         Start Docker services (Redis)"
	@echo "  make down       Stop Docker services"
	@echo "  make logs       View Docker logs"
	@echo ""
	@echo "Database:"
	@echo "  make migrate    Run database migrations"
	@echo "  make reset-db   Reset database (WARNING: destroys data)"
	@echo ""
	@echo "Quality:"
	@echo "  make test       Run tests"
	@echo "  make lint       Run linter"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean      Remove cache and compiled files"

dev:
	cp .env.development .env
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

prod:
	cp .env.production .env
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

up:
	docker-compose up -d
	@echo "Redis started at localhost:6379"

down:
	docker-compose down

logs:
	docker-compose logs -f redis

migrate:
	uv run piccolo migrations forwards cognitive

reset-db:
	rm -f cognitive.db
	rm -rf piccolo_migrations
	uv run piccolo migrations new cognitive --auto
	uv run piccolo migrations forwards cognitive

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check app/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache 2>/dev/null || true
