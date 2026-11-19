"""Consistent application logging setup."""

from __future__ import annotations

import logging
import time

from .exceptions import ConfigurationError

LOG_FORMAT = "%(asctime)sZ %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once using UTC timestamps."""

    normalized = level.upper()
    if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError(f"unsupported log level: {level}")
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        level=normalized,
        format=LOG_FORMAT,
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named project logger."""

    return logging.getLogger(name)
