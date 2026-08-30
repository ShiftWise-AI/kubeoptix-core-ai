"""Analyzer exceptions."""

from __future__ import annotations

from pathlib import Path


class AnalyzerError(Exception):
    """Base analyzer error."""


class ConfigurationError(AnalyzerError):
    """Invalid configuration or path error."""


class ParseError(AnalyzerError):
    """Error when interpreting a data file."""

    def __init__(self, message: str, *, file_path: Path | None = None) -> None:
        self.file_path = file_path
        suffix = f" ({file_path})" if file_path else ""
        super().__init__(f"{message}{suffix}")


class LoaderError(AnalyzerError):
    """Error while loading a dataset."""

    def __init__(
        self,
        message: str,
        *,
        errors: list[ParseError] | None = None,
    ) -> None:
        self.errors = errors or []
        super().__init__(message)
