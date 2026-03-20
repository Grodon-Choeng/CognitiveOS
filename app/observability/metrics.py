import logging

from app.config.settings import Settings


def configure_metrics(settings: Settings) -> None:
    logging.getLogger(__name__).info(
        "指标采集占位初始化完成。",
        extra={"app_name": settings.app_name},
    )
