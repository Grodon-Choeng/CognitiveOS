from app.application.reminders.service import ReminderApplicationService
from app.bootstrap.container import get_container


def get_reminder_service() -> ReminderApplicationService:
    return get_container().build_reminder_service()
