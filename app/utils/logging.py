import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

from app.config import settings

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    request_id_ctx.set(request_id)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        extra_fields = getattr(record, "extra_fields", None)
        if extra_fields:
            log_data.update(extra_fields)

        return json.dumps(log_data, ensure_ascii=False)


class HumanReadableFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname.ljust(8)
        base_msg = f"{self.formatTime(record)} | {level} | {record.name} | {record.getMessage()}"

        request_id = get_request_id()
        if request_id:
            base_msg = f"[{request_id[:8]}] {base_msg}"

        if record.exc_info:
            base_msg += f"\n{self.formatException(record.exc_info)}"

        return base_msg


class ExtraLogAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = kwargs.get("extra", {})
        extra_fields = self.extra.copy()
        extra.update(extra_fields)
        kwargs["extra"] = extra
        return msg, kwargs


_logger: logging.Logger | None = None


def setup_logging(
    stream: TextIO | None = None,
    structured: bool = False,
) -> logging.Logger:
    global _logger

    if _logger is not None:
        return _logger

    _logger = logging.getLogger("cognitive")
    _logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    handler = logging.StreamHandler(stream or sys.stdout)

    if structured or settings.is_production:
        formatter = StructuredFormatter()
    else:
        formatter = HumanReadableFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    _logger.addHandler(handler)

    return _logger


def get_logger(name: str | None = None) -> logging.Logger:
    global _logger

    if _logger is None:
        _logger = setup_logging()

    if name:
        return _logger.getChild(name)
    return _logger


logger = get_logger()
