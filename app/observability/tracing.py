import logging

from app.config.settings import Settings
from app.observability.context import get_observability_context


def configure_tracing(settings: Settings) -> None:
    context = get_observability_context()
    logging.getLogger(__name__).info(
        "链路追踪占位初始化完成。",
        extra={
            "app_name": settings.app_name,
            "process_role": context.process_role,
            "service_run_id": context.service_run_id,
        },
    )
