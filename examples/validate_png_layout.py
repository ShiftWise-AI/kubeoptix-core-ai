#!/usr/bin/env python3
"""
Valida a redução de margens em PNGs de relatório.

Gera pares antes/depois para gráficos numéricos e de composição, compara
dimensões e taxa de preenchimento do conteúdo, e grava um relatório em texto.

Uso:
    python examples/validate_png_layout.py
    python examples/validate_png_layout.py --output /tmp/png-validation
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt

from kubeoptix_core_ai.visualization.chart_theme import (
    CHART_COLORS,
    format_chart_percent,
    format_chart_value,
)
from kubeoptix_core_ai.visualization.models import (
    ChartDataset,
    ChartPoint,
    ChartSeries,
    CompositionDataset,
    PieSlice,
)
from kubeoptix_core_ai.visualization.png import PngRenderer
from kubeoptix_core_ai.visualization.png.postprocess import _content_bbox, optimize_png_canvas


@dataclass(frozen=True)
class ImageMetrics:
    width: int
    height: int
    fill_ratio: float
    content_bbox: tuple[int, int, int, int]

    @property
    def dimensions(self) -> str:
        return f"{self.width}x{self.height}"


def measure(path: Path) -> ImageMetrics:
    with path.open("rb") as _:
        pass
    from PIL import Image

    with Image.open(path) as image:
        left, top, right, bottom = _content_bbox(image)
        fill = ((right - left) * (bottom - top)) / (image.width * image.height)
        return ImageMetrics(
            width=image.width,
            height=image.height,
            fill_ratio=fill,
            content_bbox=(left, top, right, bottom),
        )


def _render_legacy_composition(output_path: Path) -> None:
    """Simula exportação anterior (pad_inches padrão = 0.1)."""
    slices = (
        ("Burstable", 12),
        ("Guaranteed", 5),
        ("BestEffort", 3),
    )
    labels = [label for label, _ in slices]
    values = [value for _, value in slices]
    total = sum(values)
    legend_labels = [
        f"{label} — {format_chart_percent(value, total)} ({format_chart_value(value)})"
        for label, value in zip(labels, values, strict=True)
    ]
    colors = [CHART_COLORS[index % len(CHART_COLORS)] for index in range(len(values))]

    fig, ax = plt.subplots(figsize=(8, 5))
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
    ax.set_title("Distribuição QoS (legado)", fontsize=12, fontweight="bold", pad=12)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _render_legacy_numeric(output_path: Path) -> None:
    """Simula exportação anterior (pad_inches padrão = 0.1)."""
    labels = ("api", "worker", "cache", "gateway", "batch")
    values = (320, 180, 95, 240, 150)
    import numpy as np

    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(max(8, 4 + len(labels) * 0.8), 5))
    bar_colors = [CHART_COLORS[index % len(CHART_COLORS)] for index in range(len(labels))]
    ax.bar(x, values, color=bar_colors, width=0.6, label="CPU request")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("millicores")
    ax.set_title("CPU request por workload (legado)", fontsize=12, fontweight="bold", pad=12)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _copy_and_optimize(source: Path, target: Path) -> bool:
    shutil.copy2(source, target)
    return optimize_png_canvas(target)


def _write_report(path: Path, rows: list[str]) -> None:
    header = (
        "Validação de margens PNG — kubeoptix-core-ai\n"
        "============================================\n"
    )
    path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def run_validation(output_dir: Path) -> int:
    before_dir = output_dir / "antes"
    after_dir = output_dir / "depois"
    pipeline_dir = output_dir / "pipeline_atual"
    before_dir.mkdir(parents=True, exist_ok=True)
    after_dir.mkdir(parents=True, exist_ok=True)
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    cases = (
        ("composition_qos", _render_legacy_composition),
        ("numeric_cpu", _render_legacy_numeric),
    )
    report_lines: list[str] = []
    improvements = 0

    for name, render_legacy in cases:
        legacy_path = before_dir / f"{name}.png"
        optimized_path = after_dir / f"{name}.png"
        render_legacy(legacy_path)
        changed = _copy_and_optimize(legacy_path, optimized_path)

        before = measure(legacy_path)
        after = measure(optimized_path)
        delta = after.fill_ratio - before.fill_ratio
        if delta > 0.01:
            improvements += 1

        report_lines.extend(
            [
                f"[{name}]",
                f"  legado:     {before.dimensions}  preenchimento={before.fill_ratio:.1%}  bbox={before.content_bbox}",
                f"  otimizado:  {after.dimensions}  preenchimento={after.fill_ratio:.1%}  bbox={after.content_bbox}",
                f"  dimensões preservadas: {before.dimensions == after.dimensions}",
                f"  alterado pelo optimize_png_canvas: {changed}",
                f"  ganho de área útil: {delta:+.1%}",
                "",
            ]
        )

    renderer = PngRenderer(pipeline_dir)
    renderer.render_composition(
        "qos_pipeline",
        CompositionDataset(
            title="Distribuição QoS (pipeline)",
            question="Validação",
            slices=(
                PieSlice(label="Burstable", value=12),
                PieSlice(label="Guaranteed", value=5),
                PieSlice(label="BestEffort", value=3),
            ),
        ),
    )
    renderer.render_numeric(
        "cpu_pipeline",
        ChartDataset(
            title="CPU request por workload (pipeline)",
            question="Validação",
            x_labels=("api", "worker", "cache", "gateway", "batch"),
            y_axis_label="millicores",
            series=(
                ChartSeries(
                    name="Request",
                    points=tuple(
                        ChartPoint(label=label, value=float(value), unit="m")
                        for label, value in zip(
                            ("api", "worker", "cache", "gateway", "batch"),
                            (320, 180, 95, 240, 150),
                            strict=True,
                        )
                    ),
                ),
            ),
        ),
    )

    for filename in ("qos_pipeline.png", "cpu_pipeline.png"):
        metrics = measure(pipeline_dir / filename)
        report_lines.extend(
            [
                f"[pipeline/{filename}]",
                f"  dimensões: {metrics.dimensions}",
                f"  preenchimento: {metrics.fill_ratio:.1%}",
                f"  bbox conteúdo: {metrics.content_bbox}",
                "",
            ]
        )

    _write_report(output_dir / "relatorio.txt", report_lines)

    print(f"Arquivos gerados em: {output_dir.resolve()}")
    print()
    print("Pastas:")
    print(f"  antes/          exportação legada (pad_inches=0.1)")
    print(f"  depois/         legado + optimize_png_canvas")
    print(f"  pipeline_atual/ PngRenderer com save_figure + otimização")
    print(f"  relatorio.txt   métricas detalhadas")
    print()
    for line in report_lines:
        if line.startswith("[") or line.startswith("  "):
            print(line)
    print()
    print(f"Casos com ganho > 1 p.p.: {improvements}/{len(cases)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/output/png-layout-validation"),
        help="Diretório de saída (padrão: examples/output/png-layout-validation)",
    )
    args = parser.parse_args()
    return run_validation(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
