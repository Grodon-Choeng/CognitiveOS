import logging

from app.config.settings import Settings


def configure_tracing(settings: Settings) -> None:
    logging.getLogger(__name__).info(
        "链路追踪占位初始化完成。",
        extra={"app_name": settings.app_name},
    )
