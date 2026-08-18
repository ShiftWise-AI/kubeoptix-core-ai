"""Renderização de gráficos de composição Mermaid (pie)."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.mermaid.theme import PIE_INIT
from kubeoptix_core_ai.visualization.models import CompositionDataset
from kubeoptix_core_ai.visualization.sanitize import (
    sanitize_mermaid_label,
    sanitize_mermaid_pie_title,
)


def render_pie_chart(dataset: CompositionDataset) -> str:
    """Gera bloco ``pie`` a partir de um :class:`CompositionDataset`."""
    if not dataset.slices:
        return f"{PIE_INIT}\npie title Sem dados"

    title = sanitize_mermaid_pie_title(dataset.title)
    lines = [PIE_INIT, f"pie title {title}"]
    for slice_ in dataset.slices:
        label = sanitize_mermaid_label(slice_.label)
        value = int(slice_.value) if slice_.value == int(slice_.value) else slice_.value
        lines.append(f'    "{label}" : {value}')
    return "\n".join(lines)
