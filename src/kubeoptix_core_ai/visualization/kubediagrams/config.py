"""Configuração KubeDiagrams para recursos OpenShift."""

from __future__ import annotations

from pathlib import Path

def bundled_config_path() -> Path | None:
    """Retorna o caminho do arquivo de configuração empacotado, se existir."""
    path = Path(__file__).resolve().parent / "data" / "kube-diagrams.yml"
    return path if path.is_file() else None
