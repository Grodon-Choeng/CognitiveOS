UV := uv
DOCKER_COMPOSE := docker compose
COMPOSE_SERVICES := postgres redis temporal temporal-ui

SERVICES ?= all
API_RELOAD ?= 1

.PHONY: help install infra-up infra-down infra-logs migrate api worker feishu-longconn services-up services-stop services-status services-restart fmt lint test typecheck check compose-config

help:
	@echo "可用命令："
	@echo "  make install         安装项目依赖"
	@echo "  make infra-up        启动本地基础设施"
	@echo "  make infra-down      停止本地基础设施"
	@echo "  make infra-logs      查看基础设施日志"
	@echo "  make migrate         执行数据库 migration"
	@echo "  make api             启动 FastAPI 服务"
	@echo "  make worker          启动 Temporal worker"
	@echo "  make feishu-longconn 启动飞书长连接监听"
	@echo "  make services-up     按编排启动 infra/migrate/api/worker"
	@echo "  make services-stop   按编排停止本地服务"
	@echo "  make services-status 查看本地服务状态"
	@echo "  make services-restart 按编排重启本地服务"
	@echo "  make fmt             自动修复并格式化代码"
	@echo "  make lint            执行 Ruff 检查"
	@echo "  make test            执行测试"
	@echo "  make typecheck       执行 mypy 类型检查"
	@echo "  make check           执行 lint、test、typecheck"
	@echo "  make compose-config  校验 docker compose 配置"

install:
	$(UV) sync --extra dev

infra-up:
	$(DOCKER_COMPOSE) up -d $(COMPOSE_SERVICES)

infra-down:
	$(DOCKER_COMPOSE) down

infra-logs:
	$(DOCKER_COMPOSE) logs -f --tail=200 $(COMPOSE_SERVICES)

migrate:
	$(UV) run alembic upgrade head

api:
	$(UV) run uvicorn app.main:app --reload

worker:
	$(UV) run python -m app.bootstrap.temporal

feishu-longconn:
	$(UV) run python -m app.bootstrap.feishu_long_connection

services-up:
	$(UV) run python -m app.bootstrap.services up --services "$(SERVICES)" $(if $(filter 1 true TRUE yes YES,$(API_RELOAD)),--reload,)

services-stop:
	$(UV) run python -m app.bootstrap.services down --services "$(SERVICES)"

services-status:
	$(UV) run python -m app.bootstrap.services status --services "$(SERVICES)"

services-restart:
	$(UV) run python -m app.bootstrap.services restart --services "$(SERVICES)" $(if $(filter 1 true TRUE yes YES,$(API_RELOAD)),--reload,)

fmt:
	$(UV) run ruff check --fix app tests
	$(UV) run ruff format app tests

lint:
	$(UV) run ruff check app tests

test:
	$(UV) run pytest

typecheck:
	$(UV) run mypy app tests

check: lint test typecheck

compose-config:
	$(DOCKER_COMPOSE) config
