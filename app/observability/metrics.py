import logging

from app.config.settings import Settings


def configure_metrics(settings: Settings) -> None:
    logging.getLogger(__name__).info(
        "Metrics 占位初始化完成。",
        extra={"app_name": settings.app_name},
    )
