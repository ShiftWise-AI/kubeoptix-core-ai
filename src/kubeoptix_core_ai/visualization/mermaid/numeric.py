"""Renderização legada de gráficos numéricos via Mermaid (não utilizar)."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.bar_chart import render_bar_chart
from kubeoptix_core_ai.visualization.models import ChartDataset


def render_xy_chart(dataset: ChartDataset) -> str:
    """Redireciona para :func:`render_bar_chart` (padrão do projeto)."""
    return render_bar_chart(dataset)
