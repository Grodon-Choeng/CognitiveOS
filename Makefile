.PHONY: help dev prod start stop restart status admin up down logs migrate migrate-new reset-db test test-cov lint format check clean install shell worker

help:
	@echo "CognitiveOS - Makefile Commands"
	@echo ""
	@echo "Server:"
	@echo "  make dev        Start development server (with reload)"
	@echo "  make prod       Start production server"
	@echo "  make start      Start server in background"
	@echo "  make stop       Stop server"
	@echo "  make restart    Restart server"
	@echo "  make status     Check server status"
	@echo ""
	@echo "Database:"
	@echo "  make admin      Start Piccolo Admin (http://localhost:8080)"
	@echo "  make migrate    Run pending migrations"
	@echo "  make migrate-new Create and run new migration"
	@echo "  make reset-db   Reset database (WARNING: destroys data)"
	@echo ""
	@echo "Docker:"
	@echo "  make up         Start Docker services (Redis)"
	@echo "  make down       Stop Docker services"
	@echo "  make logs       View Docker logs"
	@echo ""
	@echo "Quality:"
	@echo "  make test       Run tests"
	@echo "  make test-cov   Run tests with coverage"
	@echo "  make lint       Run linter (ruff check)"
	@echo "  make format     Format code (ruff format)"
	@echo "  make check      Run all checks (lint + test)"
	@echo ""
	@echo "Background Tasks:"
	@echo "  make worker     Start ARQ worker"
	@echo ""
	@echo "Utility:"
	@echo "  make install    Install dependencies"
	@echo "  make shell      Open Python shell with app context"
	@echo "  make clean      Remove cache and compiled files"

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

prod:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

start:
	@echo "Starting server..."
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &
	@sleep 2
	@curl -s http://localhost:8000/api/v1/health > /dev/null && echo "Server started at http://localhost:8000" || echo "Server failed to start"

stop:
	@echo "Stopping server..."
	@lsof -ti:8000 | xargs kill -9 2>/dev/null && echo "Server stopped" || echo "No server running on port 8000"

restart: stop start

status:
	@curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1 && echo "Server is running at http://localhost:8000" || echo "Server is not running"

admin:
	@echo "Starting Piccolo Admin at http://localhost:8080"
	@echo "Press Ctrl+C to stop"
	uv run uvicorn app.admin:app --reload --port 8080

up:
	docker-compose up -d
	@echo "Redis started at localhost:6379"

down:
	docker-compose down

logs:
	docker-compose logs -f redis

migrate:
	uv run piccolo migrations forwards cognitive

migrate-new:
	uv run piccolo migrations new cognitive --auto
	uv run piccolo migrations forwards cognitive

reset-db:
	@echo "WARNING: This will destroy all data!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	rm -f cognitive.db
	rm -rf piccolo_migrations
	uv run piccolo migrations new cognitive --auto
	uv run piccolo migrations forwards cognitive

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

lint:
	uv run ruff check app/

format:
	uv run ruff format app/
	uv run ruff check app/ --fix

check: lint test

worker:
	@echo "Starting ARQ worker..."
	uv run arq app.tasks.indexing.WorkerSettings

install:
	uv sync

shell:
	uv run python -i -c "from app.main import app; from app.config import settings; print('App context loaded')"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage 2>/dev/null || true
	@echo "Cleaned cache files"
