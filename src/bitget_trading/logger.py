"""Structured logging configuration."""

import logging
import sys
from typing import Any

import structlog
from structlog.types import FilteringBoundLogger


def setup_logging(log_level: str = "INFO") -> FilteringBoundLogger:
    """
    Configure structured logging with structlog.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured structlog logger
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    return structlog.get_logger()


def get_logger() -> FilteringBoundLogger:
    """Get configured logger instance."""
    return structlog.get_logger()

