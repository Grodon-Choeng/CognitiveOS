FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple

WORKDIR /app

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY dynamicconfig ./dynamicconfig

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
