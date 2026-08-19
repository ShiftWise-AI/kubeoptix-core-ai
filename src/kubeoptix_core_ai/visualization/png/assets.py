"""Utilitários para nomes de arquivos de assets PNG."""

from __future__ import annotations

import re

_ASSET_NAME_PATTERN = re.compile(r"[^\w\-]+", re.UNICODE)


def safe_asset_filename(viz_id: str) -> str:
    """Converte um ID de visualização em nome de arquivo PNG seguro."""
    safe = _ASSET_NAME_PATTERN.sub("_", viz_id).strip("_")
    return f"{safe or 'chart'}.png"
