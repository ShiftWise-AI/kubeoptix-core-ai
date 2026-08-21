"""Gráficos de composição em PNG (rosca / donut)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.visualization.chart_theme import CHART_COLORS, format_chart_percent, format_chart_value
from kubeoptix_core_ai.visualization.models import CompositionDataset
from kubeoptix_core_ai.visualization.png._mpl import matplotlib, save_figure  # noqa: F401
from kubeoptix_core_ai.visualization.png.export_config import COMPOSITION_FIGSIZE, EMPTY_CHART_FIGSIZE

import matplotlib.pyplot as plt


def _empty_chart(output_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=EMPTY_CHART_FIGSIZE)
    ax.axis("off")
    ax.text(0.5, 0.5, "Sem dados para exibir", ha="center", va="center", fontsize=12, color="#666666")
    ax.set_title(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    save_figure(fig, output_path)
    plt.close(fig)


def render_composition_png(dataset: CompositionDataset, output_path: Path) -> None:
    """Gera PNG de rosca a partir de um :class:`CompositionDataset`."""
    if not dataset.slices:
        _empty_chart(output_path, dataset.title)
        return

    total = sum(slice_.value for slice_ in dataset.slices)
    if total <= 0:
        _empty_chart(output_path, dataset.title)
        return

    labels = [slice_.label for slice_ in dataset.slices]
    values = [slice_.value for slice_ in dataset.slices]
    colors = [CHART_COLORS[index % len(CHART_COLORS)] for index in range(len(values))]
    legend_labels = [
        f"{label} — {format_chart_percent(value, total)} ({format_chart_value(value)})"
        for label, value in zip(labels, values, strict=True)
    ]

    fig, ax = plt.subplots(figsize=COMPOSITION_FIGSIZE)
    wedges, *_ = ax.pie(
        values,
        labels=None,
        colors=colors,
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1},
    )
    ax.legend(
        wedges,
        legend_labels,
        loc="center left",
        bbox_to_anchor=(1, 0.5),
        fontsize=9,
        frameon=False,
    )
    ax.text(0, 0, format_chart_value(total), ha="center", va="center", fontsize=14, fontweight="bold")
    ax.set_title(dataset.title, fontsize=12, fontweight="bold", pad=12)
    fig.tight_layout()
    save_figure(fig, output_path)
    plt.close(fig)
