"""Analyzer logging configuration."""

from __future__ import annotations

import logging
import sys

_LOGGER_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the package root logger in an idempotent way."""
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger("kubeoptix_core_ai")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False
    _LOGGER_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger for the package namespace."""
    return logging.getLogger(f"kubeoptix_core_ai.{name}")
