"""Utilitários base para parsing de YAML."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.logging import get_logger

logger = get_logger("parsers.base")

# Valores sanitizados como ``[TOKEN_REMOVIDO].io`` quebram o parser YAML
# (colchetes são interpretados como flow sequence).
_BRACKET_SCALAR_RE = re.compile(
    r"^(\s+)(\w+): (\[[^\]]+\]\S.*)$",
    re.MULTILINE,
)


def _sanitize_yaml_text(text: str) -> str:
    """Aspas em escalares com colchetes seguidos de sufixo (ex.: tokens redigidos)."""

    def _quote(match: re.Match[str]) -> str:
        indent, key, value = match.group(1), match.group(2), match.group(3)
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{indent}{key}: "{escaped}"'

    return _BRACKET_SCALAR_RE.sub(_quote, text)


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
        document = yaml.safe_load(_sanitize_yaml_text(text))
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
