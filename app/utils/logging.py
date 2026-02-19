import sys
import logging
from typing import TextIO

from app.config import settings


def setup_logging(stream: TextIO | None = None) -> logging.Logger:
    _logger = logging.getLogger("cognitive")
    _logger.setLevel(getattr(logging, settings.log_level.upper()))

    if not _logger.handlers:
        handler = logging.StreamHandler(stream or sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        _logger.addHandler(handler)

    return _logger


logger = setup_logging()
