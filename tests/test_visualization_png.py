"""Testes do renderizador PNG."""

from __future__ import annotations

from pathlib import Path

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
from kubeoptix_core_ai.visualization.png import PngRenderer
from kubeoptix_core_ai.visualization.png.assets import safe_asset_filename


def test_safe_asset_filename() -> None:
    assert safe_asset_filename("cpu_request") == "cpu_request.png"
    assert safe_asset_filename("ext_comm/route-a") == "ext_comm_route-a.png"


def test_render_numeric_png(tmp_path: Path) -> None:
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
    renderer = PngRenderer(tmp_path, path_prefix="assets")
    rel = renderer.render_numeric("cpu_request", dataset)
    assert rel == "assets/cpu_request.png"
    assert (tmp_path / "cpu_request.png").is_file()
    assert (tmp_path / "cpu_request.png").stat().st_size > 0


def test_render_composition_png(tmp_path: Path) -> None:
    dataset = CompositionDataset(
        title="QoS",
        question="Test",
        slices=(
            PieSlice(label="Burstable", value=2),
            PieSlice(label="Guaranteed", value=1),
        ),
    )
    renderer = PngRenderer(tmp_path)
    rel = renderer.render_composition("qos", dataset)
    assert rel == "qos.png"
    assert (tmp_path / "qos.png").is_file()


def test_render_flowchart_png(tmp_path: Path) -> None:
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
    renderer = PngRenderer(tmp_path)
    rel = renderer.render_flowchart("comm", dataset)
    assert rel == "comm.png"
    assert (tmp_path / "comm.png").is_file()
