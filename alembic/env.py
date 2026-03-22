from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config.settings import get_settings
from app.infrastructure.db.base import Base
from app.infrastructure.db.models.conversation_binding import ConversationBindingModel
from app.infrastructure.db.models.memory import MemoryModel
from app.infrastructure.db.models.message_event import MessageEventLogModel
from app.infrastructure.db.models.model_invocation import ModelInvocationLogModel
from app.infrastructure.db.models.reminder import ReminderModel
from app.infrastructure.db.models.task import TaskModel
from app.infrastructure.db.models.tool_invocation import ToolInvocationLogModel
from app.infrastructure.db.models.workflow_event import WorkflowEventLogModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

_ = (
    ConversationBindingModel,
    MessageEventLogModel,
    MemoryModel,
    ReminderModel,
    TaskModel,
    ModelInvocationLogModel,
    ToolInvocationLogModel,
    WorkflowEventLogModel,
)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def run_async_migrations() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

        await connectable.dispose()

    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
