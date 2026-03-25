import logging
from logging import Filter, LogRecord
from logging.config import dictConfig
from pathlib import Path

from app.config.settings import Settings
from app.observability.context import get_observability_context


class ObservabilityContextFilter(Filter):
    def filter(self, record: LogRecord) -> bool:
        context = get_observability_context()
        record.trace_id = getattr(record, "trace_id", None) or context.trace_id or "-"
        record.chain_id = getattr(record, "chain_id", None) or context.chain_id or "-"
        record.request_id = getattr(record, "request_id", None) or context.request_id or "-"
        record.process_role = (
            getattr(record, "process_role", None) or context.process_role or "manual"
        )
        record.service_run_id = (
            getattr(record, "service_run_id", None) or context.service_run_id or "manual"
        )
        return True


def configure_logging(settings: Settings) -> None:
    handlers: dict[str, dict[str, object]] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["observability_context"],
        },
    }
    root_handlers = ["console"]
    if settings.log_file_enabled:
        process_role = get_observability_context().process_role or "manual"
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filters": ["observability_context"],
            "filename": str(log_dir / f"{process_role}.log"),
            "encoding": "utf-8",
        }
        root_handlers.append("file")

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "observability_context": {
                    "()": ObservabilityContextFilter,
                },
            },
            "formatters": {
                "default": {
                    "format": (
                        "%(asctime)s %(levelname)s [%(name)s] "
                        "[role=%(process_role)s run=%(service_run_id)s "
                        "trace=%(trace_id)s chain=%(chain_id)s request=%(request_id)s] "
                        "%(message)s"
                    ),
                },
            },
            "handlers": handlers,
            "root": {
                "handlers": root_handlers,
                "level": "DEBUG" if settings.debug else "INFO",
            },
        }
    )
    logging.getLogger(__name__).info("日志系统初始化完成。")
