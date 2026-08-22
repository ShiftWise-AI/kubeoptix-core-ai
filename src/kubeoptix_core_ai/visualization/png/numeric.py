"""Gráficos numéricos em PNG (barras e linhas)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.visualization.chart_theme import (
    CHART_AXIS_COLOR,
    CHART_COLORS,
    CHART_MUTED_COLOR,
    truncate_chart_label,
)
from kubeoptix_core_ai.visualization.models import ChartDataset, ChartPoint, ChartSeries
from kubeoptix_core_ai.visualization.png._mpl import matplotlib, save_figure  # noqa: F401
from kubeoptix_core_ai.visualization.png.export_config import (
    EMPTY_CHART_FIGSIZE,
    NUMERIC_FIGSIZE_HEIGHT,
    numeric_figsize_width,
)

import matplotlib.pyplot as plt
import numpy as np


def _format_point(point: ChartPoint) -> str:
    value = int(point.value) if point.value == int(point.value) else round(point.value, 1)
    unit = point.unit.strip()
    return f"{value} {unit}".strip() if unit else str(value)


def _bar_series(dataset: ChartDataset) -> tuple[ChartSeries, ...]:
    return tuple(series for series in dataset.series if series.series_type == "bar")


def _line_series(dataset: ChartDataset) -> tuple[ChartSeries, ...]:
    return tuple(series for series in dataset.series if series.series_type == "line")


def _compute_y_max(dataset: ChartDataset) -> float:
    if dataset.y_max is not None:
        return dataset.y_max
    max_val = 0.0
    for series in dataset.series:
        for point in series.points:
            max_val = max(max_val, point.value)
    return max(max_val * 1.1, 1.0)


def _point_for(series: ChartSeries, label: str) -> ChartPoint | None:
    for point in series.points:
        if point.label == label:
            return point
    return None


def _empty_chart(output_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=EMPTY_CHART_FIGSIZE)
    ax.axis("off")
    ax.text(0.5, 0.5, "Sem dados para exibir", ha="center", va="center", fontsize=12, color=CHART_MUTED_COLOR)
    ax.set_title(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    save_figure(fig, output_path)
    plt.close(fig)


def render_numeric_png(dataset: ChartDataset, output_path: Path) -> None:
    """Gera PNG de barras (e linhas opcionais) a partir de um :class:`ChartDataset`."""
    bars = _bar_series(dataset)
    lines = _line_series(dataset)
    if not dataset.x_labels or (not bars and not lines):
        _empty_chart(output_path, dataset.title)
        return

    labels = list(dataset.x_labels)
    x = np.arange(len(labels))
    y_max = _compute_y_max(dataset)
    fig_width = numeric_figsize_width(len(labels))
    fig, ax = plt.subplots(figsize=(fig_width, NUMERIC_FIGSIZE_HEIGHT))

    if bars:
        if len(bars) == 1:
            values = [
                (_point_for(bars[0], label).value if _point_for(bars[0], label) else 0.0)
                for label in labels
            ]
            colors = [CHART_COLORS[index % len(CHART_COLORS)] for index in range(len(labels))]
            ax.bar(x, values, color=colors, width=0.6, label=bars[0].name)
        else:
            width = 0.8 / len(bars)
            for series_index, series in enumerate(bars):
                values = [
                    (_point_for(series, label).value if _point_for(series, label) else 0.0)
                    for label in labels
                ]
                offset = (series_index - (len(bars) - 1) / 2) * width
                color = CHART_COLORS[series_index % len(CHART_COLORS)]
                ax.bar(x + offset, values, width=width * 0.9, color=color, label=series.name)

    for series_index, series in enumerate(lines):
        values = [
            (_point_for(series, label).value if _point_for(series, label) else 0.0)
            for label in labels
        ]
        color = CHART_COLORS[(len(bars) + series_index) % len(CHART_COLORS)]
        ax.plot(x, values, color=color, marker="o", linewidth=2, label=series.name)

    short_labels = [truncate_chart_label(label, 16) for label in labels]
    rotation = 0 if len(labels) <= 5 and max(len(label) for label in labels) <= 14 else 35
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, rotation=rotation, ha="right" if rotation else "center")
    ax.set_ylabel(dataset.y_axis_label)
    ax.set_xlabel(dataset.x_axis_label)
    ax.set_ylim(0, y_max)
    ax.set_title(dataset.title, fontsize=12, fontweight="bold", pad=12)
    ax.grid(axis="y", linestyle="--", color=CHART_AXIS_COLOR)
    if len(bars) > 1 or lines:
        ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    save_figure(fig, output_path)
    plt.close(fig)
