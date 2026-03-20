from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.reminders.ports import ReminderUnitOfWorkFactory
from app.application.reminders.service import ReminderApplicationService
from app.config.settings import Settings, get_settings
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.db.uow import SQLAlchemyReminderUnitOfWork
from app.infrastructure.temporal.gateway import TemporalReminderWorkflowGateway
from app.observability.model_invocations import (
    DatabaseModelInvocationRecorder,
    JsonlModelInvocationRecorder,
    MultiModelInvocationRecorder,
)
from app.observability.tool_invocations import (
    DatabaseToolInvocationRecorder,
    JsonlToolInvocationRecorder,
    MultiToolInvocationRecorder,
)


class ApplicationContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session_factory: async_sessionmaker = get_session_factory(settings)
        self.workflow_gateway = TemporalReminderWorkflowGateway(settings=settings)

    def build_reminder_service(self) -> ReminderApplicationService:
        return ReminderApplicationService(
            unit_of_work_factory=self.build_reminder_unit_of_work_factory(),
            workflow_gateway=self.workflow_gateway,
        )

    def build_reminder_unit_of_work_factory(self) -> ReminderUnitOfWorkFactory:
        def create_unit_of_work() -> SQLAlchemyReminderUnitOfWork:
            return SQLAlchemyReminderUnitOfWork(self.session_factory)

        return create_unit_of_work

    def build_model_invocation_recorder(self) -> MultiModelInvocationRecorder:
        return MultiModelInvocationRecorder(
            [
                DatabaseModelInvocationRecorder(
                    session_factory=self.session_factory,
                    enabled=self.settings.model_invocation_db_enabled,
                ),
                JsonlModelInvocationRecorder(
                    path=self.settings.model_invocation_jsonl_path,
                    enabled=self.settings.model_invocation_jsonl_enabled,
                ),
            ]
        )

    def build_tool_invocation_recorder(self) -> MultiToolInvocationRecorder:
        return MultiToolInvocationRecorder(
            [
                DatabaseToolInvocationRecorder(
                    session_factory=self.session_factory,
                    enabled=self.settings.tool_invocation_db_enabled,
                ),
                JsonlToolInvocationRecorder(
                    path=self.settings.tool_invocation_jsonl_path,
                    enabled=self.settings.tool_invocation_jsonl_enabled,
                ),
            ]
        )


@lru_cache
def get_container() -> ApplicationContainer:
    return ApplicationContainer(settings=get_settings())
