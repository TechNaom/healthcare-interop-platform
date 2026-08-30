"""Structured logging configuration (structlog).

``configure_logging`` sets up JSON logs (or a console renderer in dev) once at
process start; ``get_logger`` returns a bound logger. Callers pass explicit
key/value fields and must include only non-PHI values — the no-PHI-in-logs test
(tests) guards this at the workload level.
"""

from __future__ import annotations

import logging
import os

import structlog
from structlog.types import Processor


def configure_logging(*, json_logs: bool | None = None, level: str | None = None) -> None:
    """Configure structlog + stdlib logging. Idempotent enough for app startup.

    JSON by default (override with ``json_logs`` or ``HIP_LOG_JSON=0`` for a
    human-readable console in local dev).
    """
    use_json = json_logs if json_logs is not None else os.environ.get("HIP_LOG_JSON", "1") != "0"
    log_level = (level or os.environ.get("HIP_LOG_LEVEL", "INFO")).upper()

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    renderer: Processor = (
        structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer()
    )

    logging.basicConfig(format="%(message)s", level=getattr(logging, log_level, logging.INFO))
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """A bound structured logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
