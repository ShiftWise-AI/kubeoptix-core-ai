"""Renderização legada de composição via Mermaid pie (não utilizar)."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.doughnut_chart import render_doughnut_chart
from kubeoptix_core_ai.visualization.models import CompositionDataset


def render_pie_chart(dataset: CompositionDataset) -> str:
    """Redireciona para :func:`render_doughnut_chart` (padrão do projeto)."""
    return render_doughnut_chart(dataset)
