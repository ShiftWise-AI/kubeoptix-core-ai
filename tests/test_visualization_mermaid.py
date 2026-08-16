"""Testes do gerador Mermaid."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.mermaid import MermaidGenerator
from kubeoptix_core_ai.visualization.models import (
    DiagramEdge,
    DiagramNode,
    FlowchartDataset,
)


def test_render_flowchart() -> None:
    dataset = FlowchartDataset(
        title="Comm",
        question="Test",
        nodes=(
            DiagramNode(id="svc_a", node_type="service", label="Service/a"),
            DiagramNode(id="wl_a", node_type="workload", label="Deployment/a"),
        ),
        edges=(
            DiagramEdge(
                source_id="svc_a",
                target_id="wl_a",
                edge_type="selects",
            ),
        ),
    )
    mermaid = MermaidGenerator().render_flowchart(dataset)
    assert mermaid.startswith("flowchart LR")
    assert 'svc_a[("Service/a")]' in mermaid or 'svc_a["Service/a"]' in mermaid
    assert "-->" in mermaid
