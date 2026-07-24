"""Structured logging setup.

Uses the standard library logging module with a compact, greppable format.
Swap the formatter here if/when structured JSON log shipping is required in
production (see docs/db 19-Scale-Review.md for the observability direction).
"""

import logging
import sys

from nivesh.config import get_settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging() -> None:
    settings = get_settings()

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy third-party loggers by default.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
