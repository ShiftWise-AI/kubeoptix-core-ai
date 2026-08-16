"""Testes do componente DoughnutChart."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.doughnut_chart import (
    DoughnutChart,
    DoughnutChartConfig,
    render_doughnut_chart,
)
from kubeoptix_core_ai.visualization.models import CompositionDataset, PieSlice


def test_doughnut_chart_renders_svg_with_hole_and_legend() -> None:
    dataset = CompositionDataset(
        title="Distribuição de QoS",
        question="Test",
        slices=(
            PieSlice(label="Burstable", value=2),
            PieSlice(label="Guaranteed", value=1),
        ),
    )
    html = render_doughnut_chart(dataset)

    assert "kubeoptix-doughnut" in html
    assert "<svg" in html
    assert "Burstable — 67%" in html or "Burstable — 66" in html
    assert "Guaranteed — 33%" in html or "Guaranteed — 33" in html
    assert ">3<" in html
    assert "pie title" not in html
    assert "<title>Burstable:" in html


def test_doughnut_chart_legend_on_right_layout() -> None:
    html = DoughnutChart(
        CompositionDataset(
            title="Findings",
            question="Test",
            slices=(PieSlice(label="High", value=1),),
        )
    ).render()

    assert 'display:flex' in html
    assert "border-radius:50%" in html
    assert "High — 100%" in html


def test_doughnut_chart_empty_state() -> None:
    html = render_doughnut_chart(
        CompositionDataset(title="Vazio", question="Test", slices=())
    )
    assert "Sem dados para exibir" in html


def test_doughnut_chart_custom_center_label() -> None:
    html = DoughnutChart(
        CompositionDataset(
            title="QoS",
            question="Test",
            slices=(PieSlice(label="A", value=1), PieSlice(label="B", value=1)),
        ),
        config=DoughnutChartConfig(center_label="Total", show_center_total=True),
    ).render()

    assert ">Total<" in html
