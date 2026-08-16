"""Testes do gerador Mermaid."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.mermaid import MermaidGenerator
from kubeoptix_core_ai.visualization.models import (
    ChartDataset,
    ChartPoint,
    ChartSeries,
    CompositionDataset,
    DiagramEdge,
    DiagramNode,
    FlowchartDataset,
    PieSlice,
)


def test_render_xy_chart() -> None:
    dataset = ChartDataset(
        title="CPU request",
        question="Test",
        x_labels=("wl-a", "wl-b"),
        y_axis_label="millicores",
        series=(
            ChartSeries(
                name="Request",
                points=(
                    ChartPoint(label="wl-a", value=100, unit="m"),
                    ChartPoint(label="wl-b", value=200, unit="m"),
                ),
            ),
        ),
    )
    mermaid = MermaidGenerator().render_numeric(dataset)
    assert mermaid.startswith("%%{init:")
    assert "xychart-beta" in mermaid
    assert "wl_a" in mermaid or "wl-a" in mermaid
    assert "100" in mermaid
    assert "200" in mermaid


def test_render_pie_chart() -> None:
    dataset = CompositionDataset(
        title="QoS",
        question="Test",
        slices=(
            PieSlice(label="Burstable", value=2),
            PieSlice(label="Guaranteed", value=1),
        ),
    )
    mermaid = MermaidGenerator().render_composition(dataset)
    assert "pie title QoS" in mermaid
    assert "%%{init:" in mermaid
    assert "Burstable" in mermaid
    assert ": 2" in mermaid


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
