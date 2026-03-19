from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.reminders.ports import ReminderUnitOfWorkFactory
from app.application.reminders.service import ReminderApplicationService
from app.config.settings import Settings, get_settings
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.db.uow import SQLAlchemyReminderUnitOfWork
from app.infrastructure.temporal.gateway import TemporalReminderWorkflowGateway


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
        return lambda: SQLAlchemyReminderUnitOfWork(self.session_factory)


@lru_cache
def get_container() -> ApplicationContainer:
    return ApplicationContainer(settings=get_settings())
