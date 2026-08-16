"""Sanitização de identificadores para diagramas Mermaid."""

from __future__ import annotations

import re

_INVALID_ID_CHARS = re.compile(r"[^a-zA-Z0-9_]")
_LEADING_DIGIT = re.compile(r"^[0-9]")


def sanitize_mermaid_id(raw: str, *, prefix: str = "n") -> str:
    """
    Converte um rótulo arbitrário em ID válido para nós Mermaid.

    Mermaid exige IDs alfanuméricos (underscore permitido) e não pode
    começar com dígito.
    """
    cleaned = _INVALID_ID_CHARS.sub("_", raw.strip())
    if not cleaned or not cleaned.replace("_", ""):
        cleaned = prefix
    if _LEADING_DIGIT.match(cleaned):
        cleaned = f"{prefix}_{cleaned}"
    return cleaned


def sanitize_mermaid_label(raw: str) -> str:
    """Escapa caracteres problemáticos em rótulos entre aspas duplas."""
    text = raw.replace("\\", "/")
    text = text.replace('"', "'")
    text = text.replace("[", "(").replace("]", ")")
    text = text.replace("\n", "<br/>")
    text = text.replace("\r", "")
    return text


def sanitize_mermaid_pie_title(raw: str) -> str:
    """
    Título para ``pie title`` sem aspas (sintaxe oficial Mermaid).

    Aspas no título aparecem literalmente no gráfico e quebram em alguns renderers.
    """
    text = sanitize_mermaid_label(raw)
    return text.replace(":", " -")


def sanitize_mermaid_edge_label(raw: str) -> str:
    """Rótulo de aresta flowchart; aspas só quando necessário para parênteses."""
    text = sanitize_mermaid_label(raw)
    if any(char in text for char in '()"#'):
        return f'"{text}"'
    return text


def label_needs_rect_node_shape(label: str) -> bool:
    """
    Parênteses/colchetes em formas stadium/cylinder quebram o parser.

    Colchetes no rótulo bruto viram parênteses após :func:`sanitize_mermaid_label`.
    """
    if any(char in label for char in "()[]"):
        return True
    sanitized = sanitize_mermaid_label(label)
    return "(" in sanitized or ")" in sanitized
