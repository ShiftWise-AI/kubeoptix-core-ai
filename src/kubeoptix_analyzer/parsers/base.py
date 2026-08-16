"""Utilitários base para parsing de YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from kubeoptix_analyzer.errors import ParseError
from kubeoptix_analyzer.logging import get_logger

logger = get_logger("parsers.base")


def load_yaml_file(file_path: Path) -> Any:
    """
    Carrega um documento YAML de um arquivo.

    Levanta ParseError se o arquivo não puder ser interpretado.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"Não foi possível ler o arquivo: {exc}", file_path=file_path) from exc

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ParseError(f"YAML inválido: {exc}", file_path=file_path) from exc

    if document is None:
        raise ParseError("Documento YAML vazio", file_path=file_path)

    if not isinstance(document, dict):
        raise ParseError(
            f"Documento YAML deve ser um mapeamento, recebido {type(document).__name__}",
            file_path=file_path,
        )

    return document


def get_nested(data: dict, *keys: str, default: Any = None) -> Any:
    """Acessa chaves aninhadas com fallback."""
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current
