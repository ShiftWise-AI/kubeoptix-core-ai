"""Testes do componente BarChart."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.bar_chart import BarChart, render_bar_chart
from kubeoptix_core_ai.visualization.models import ChartDataset, ChartPoint, ChartSeries


def test_bar_chart_single_series_uses_lateral_legend_and_x_axis() -> None:
    dataset = ChartDataset(
        title="CPU request",
        question="Test",
        x_labels=("wl-a", "wl-b"),
        y_axis_label="CPU (millicores)",
        x_axis_label="Workload",
        series=(
            ChartSeries(
                name="CPU request",
                points=(
                    ChartPoint(label="wl-a", value=100, unit="m"),
                    ChartPoint(label="wl-b", value=200, unit="m"),
                ),
            ),
        ),
    )
    html = render_bar_chart(dataset)

    assert "kubeoptix-bar-chart" in html
    assert "wl-a — 100 m" in html
    assert "wl-b — 200 m" in html
    assert ">Workload<" in html
    assert ">wl-a<" in html
    assert ">wl-b<" in html
    assert "<title>wl-a: 100 m</title>" in html
    assert 'transform="rotate(-90' in html
    assert ">CPU (millicores)<" in html


def test_bar_chart_multi_series_x_axis_labels_and_legend() -> None:
    html = BarChart(
        ChartDataset(
            title="CPU request x limit",
            question="Test",
            x_labels=("wl-a", "wl-b"),
            y_axis_label="CPU (millicores)",
            x_axis_label="Workload",
            series=(
                ChartSeries(
                    name="Request",
                    points=(
                        ChartPoint(label="wl-a", value=100, unit="m"),
                        ChartPoint(label="wl-b", value=150, unit="m"),
                    ),
                ),
                ChartSeries(
                    name="Limit",
                    points=(
                        ChartPoint(label="wl-a", value=200, unit="m"),
                        ChartPoint(label="wl-b", value=300, unit="m"),
                    ),
                ),
            ),
        )
    ).render()

    assert ">Request<" in html
    assert ">Limit<" in html
    assert ">Workload<" in html
    assert ">wl-a<" in html
    assert "wl-a · Request: 100 m" in html


def test_bar_chart_rotates_long_x_labels() -> None:
    long_name = "backend-acesso-application-with-very-long-name"
    html = render_bar_chart(
        ChartDataset(
            title="CPU",
            question="Test",
            x_labels=(long_name, "other"),
            y_axis_label="CPU (millicores)",
            x_axis_label="Workload",
            series=(
                ChartSeries(
                    name="CPU request",
                    points=(
                        ChartPoint(label=long_name, value=100, unit="m"),
                        ChartPoint(label="other", value=50, unit="m"),
                    ),
                ),
            ),
        )
    )

    assert "rotate(-" in html
    assert html.count("…") >= 1
    assert f"<title>{long_name}</title>" in html


def test_bar_chart_empty_state() -> None:
    html = render_bar_chart(
        ChartDataset(
            title="Vazio",
            question="Test",
            x_labels=(),
            y_axis_label="m",
            series=(),
        )
    )
    assert "Sem dados para exibir" in html
