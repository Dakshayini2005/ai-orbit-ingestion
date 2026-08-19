"""Structured logging. One logger per module via get_logger(__name__).

Log lines are formatted as: timestamp | level | logger | event_key=value ...
which is grep-able and good enough for this project's scale without pulling
in a JSON-logging dependency.
"""
from __future__ import annotations

import logging
import sys

from src.config.settings import settings

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.handlers = [handler]
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)


def kv(**fields) -> str:
    """Render keyword fields as `key=value` pairs for structured-ish logging.

    Never pass raw secrets here — callers are responsible for redacting
    tokens/keys before logging (see discovery adapters, which never log
    Authorization headers or key query params).
    """
    return " ".join(f"{k}={v!r}" for k, v in fields.items())
