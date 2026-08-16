"""Renderização de datasets em sintaxe Mermaid."""

from __future__ import annotations

from kubeoptix_analyzer.visualization.mermaid.composition import render_pie_chart
from kubeoptix_analyzer.visualization.mermaid.flowchart import render_flowchart
from kubeoptix_analyzer.visualization.mermaid.numeric import render_xy_chart
from kubeoptix_analyzer.visualization.models import (
    ChartDataset,
    CompositionDataset,
    FlowchartDataset,
)


class MermaidGenerator:
    """Converte datasets estruturados em blocos Mermaid."""

    def render_numeric(self, dataset: ChartDataset) -> str:
        return render_xy_chart(dataset)

    def render_composition(self, dataset: CompositionDataset) -> str:
        return render_pie_chart(dataset)

    def render_flowchart(self, dataset: FlowchartDataset) -> str:
        return render_flowchart(dataset)
