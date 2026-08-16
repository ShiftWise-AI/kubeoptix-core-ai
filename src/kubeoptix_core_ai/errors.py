"""Exceções do analisador."""

from __future__ import annotations

from pathlib import Path


class AnalyzerError(Exception):
    """Erro base do analisador."""


class ConfigurationError(AnalyzerError):
    """Erro de configuração ou caminho inválido."""


class ParseError(AnalyzerError):
    """Erro ao interpretar um arquivo de dados."""

    def __init__(self, message: str, *, file_path: Path | None = None) -> None:
        self.file_path = file_path
        suffix = f" ({file_path})" if file_path else ""
        super().__init__(f"{message}{suffix}")


class LoaderError(AnalyzerError):
    """Erro ao carregar um conjunto de dados."""

    def __init__(
        self,
        message: str,
        *,
        errors: list[ParseError] | None = None,
    ) -> None:
        self.errors = errors or []
        super().__init__(message)
