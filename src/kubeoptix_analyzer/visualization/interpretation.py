"""Texto interpretativo curto para visualizações."""

from __future__ import annotations

from kubeoptix_analyzer.visualization.models import (
    ChartDataset,
    CompositionDataset,
    FlowchartDataset,
)


def interpret_visualization(
    dataset: ChartDataset | CompositionDataset | FlowchartDataset,
) -> str:
    if isinstance(dataset, ChartDataset):
        return _interpret_numeric(dataset)
    if isinstance(dataset, CompositionDataset):
        return _interpret_composition(dataset)
    return _interpret_flowchart(dataset)


def _interpret_numeric(dataset: ChartDataset) -> str:
    series_names = ", ".join(s.name for s in dataset.series)
    return (
        f"**Fato observado / valor calculado:** gráfico derivado dos Deployments e "
        f"worknodes coletados. Séries: {series_names}. "
        f"Valores agregados do namespace são **cálculos** (soma request × réplicas). "
        f"Não confundir com uso real (PodMetrics)."
    )


def _interpret_composition(dataset: CompositionDataset) -> str:
    total = sum(s.value for s in dataset.slices)
    parts = ", ".join(f"{s.label}: {int(s.value)}" for s in dataset.slices)
    return (
        f"**Valor calculado:** distribuição entre {int(total)} unidade(s) — {parts}. "
        f"Contagens derivadas dos dados ingeridos, sem inferência adicional."
    )


def _interpret_flowchart(dataset: FlowchartDataset) -> str:
    edge_types = {e.edge_type for e in dataset.edges}
    return (
        f"**Fato observado:** {len(dataset.nodes)} nó(s) e {len(dataset.edges)} "
        f"relação(ões) com evidência nos artefatos YAML. "
        f"Tipos de relação: {', '.join(sorted(edge_types)) or 'nenhum'}. "
        f"Arestas sem evidência não são exibidas. Comunicação Pod→Pod não inferida."
    )
