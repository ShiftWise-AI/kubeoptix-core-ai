"""Componente reutilizável de Doughnut Chart para gráficos de composição."""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

from kubeoptix_core_ai.visualization.chart_theme import (
    CHART_COLORS,
    build_chart_id,
    chart_container_open,
    chart_empty_state,
    chart_legend_close,
    chart_legend_open,
    chart_plot_close,
    chart_plot_open,
    format_chart_percent,
    format_chart_value,
    legend_item,
)
from kubeoptix_core_ai.visualization.models import CompositionDataset


@dataclass(frozen=True)
class DoughnutChartConfig:
    """Opções visuais compartilhadas por todos os Doughnut Charts do projeto."""

    colors: tuple[str, ...] = CHART_COLORS
    size: int = 220
    inner_radius_ratio: float = 0.58
    show_center_total: bool = True
    center_label: str | None = None


def _polar(cx: float, cy: float, radius: float, angle_deg: float) -> tuple[float, float]:
    angle_rad = math.radians(angle_deg - 90)
    return cx + radius * math.cos(angle_rad), cy + radius * math.sin(angle_rad)


def _describe_donut_segment(
    cx: float,
    cy: float,
    inner_r: float,
    outer_r: float,
    start_angle: float,
    end_angle: float,
) -> str:
    sweep = end_angle - start_angle
    if sweep <= 0:
        return ""
    if sweep >= 360:
        sweep = 359.999
        end_angle = start_angle + sweep

    start_outer = _polar(cx, cy, outer_r, start_angle)
    end_outer = _polar(cx, cy, outer_r, end_angle)
    start_inner = _polar(cx, cy, inner_r, end_angle)
    end_inner = _polar(cx, cy, inner_r, start_angle)
    large_arc = 1 if sweep > 180 else 0

    return (
        f"M {start_outer[0]:.2f} {start_outer[1]:.2f} "
        f"A {outer_r} {outer_r} 0 {large_arc} 1 {end_outer[0]:.2f} {end_outer[1]:.2f} "
        f"L {start_inner[0]:.2f} {start_inner[1]:.2f} "
        f"A {inner_r} {inner_r} 0 {large_arc} 0 {end_inner[0]:.2f} {end_inner[1]:.2f} "
        f"Z"
    )


class DoughnutChart:
    """Renderiza gráficos de rosca com legenda lateral e tooltip nativo."""

    _SEGMENT_CLASS = "kubeoptix-doughnut-segment"
    _CSS_CLASS = "kubeoptix-doughnut"

    def __init__(
        self,
        dataset: CompositionDataset,
        config: DoughnutChartConfig | None = None,
    ) -> None:
        self.dataset = dataset
        self.config = config or DoughnutChartConfig()

    def render(self) -> str:
        if not self.dataset.slices:
            return chart_empty_state(self._CSS_CLASS, self.dataset.title)

        total = sum(slice_.value for slice_ in self.dataset.slices)
        if total <= 0:
            return chart_empty_state(self._CSS_CLASS, self.dataset.title)

        cfg = self.config
        size = cfg.size
        cx = cy = size / 2
        outer_r = (size / 2) - 8
        inner_r = outer_r * cfg.inner_radius_ratio
        chart_id = self._chart_id()

        segments: list[str] = []
        legend_items: list[str] = []
        angle = 0.0

        for index, slice_ in enumerate(self.dataset.slices):
            color = cfg.colors[index % len(cfg.colors)]
            sweep = (slice_.value / total) * 360
            if sweep <= 0:
                continue
            end_angle = angle + sweep
            path = _describe_donut_segment(cx, cy, inner_r, outer_r, angle, end_angle)
            if not path:
                angle = end_angle
                continue

            label = html.escape(slice_.label)
            value_text = format_chart_value(slice_.value)
            percent_text = format_chart_percent(slice_.value, total)
            tooltip = f"{slice_.label}: {value_text} ({percent_text})"

            segments.append(
                f'<path class="{self._SEGMENT_CLASS}" d="{path}" fill="{color}" '
                f'data-label="{label}">'
                f"<title>{html.escape(tooltip)}</title></path>"
            )
            legend_items.append(
                legend_item(
                    color,
                    f"{label} — {html.escape(percent_text)}",
                    tooltip,
                    circular=True,
                )
            )
            angle = end_angle

        center_text = html.escape(cfg.center_label or format_chart_value(total))
        parts = [
            chart_container_open(
                chart_id,
                self._CSS_CLASS,
                self.dataset.title,
                segment_class=self._SEGMENT_CLASS,
            ),
            chart_plot_open(),
            f'<div style="position:relative;width:{size}px;height:{size}px;flex-shrink:0;">',
            f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" aria-hidden="true">',
            "".join(segments),
            "</svg>",
            (
                f'<div style="position:absolute;inset:0;display:flex;align-items:center;'
                f"justify-content:center;text-align:center;font-size:20px;font-weight:600;"
                f'line-height:1.1;pointer-events:none;">'
                f"{center_text if cfg.show_center_total else ''}</div>"
            ),
            "</div>",
            chart_plot_close(),
            chart_legend_open(),
            "".join(legend_items),
            chart_legend_close(),
        ]
        return "".join(parts)

    def _chart_id(self) -> str:
        fingerprint = "|".join(
            f"{slice_.label}:{slice_.value}" for slice_ in self.dataset.slices
        )
        return build_chart_id("doughnut", self.dataset.title, fingerprint)


def render_doughnut_chart(
    dataset: CompositionDataset,
    config: DoughnutChartConfig | None = None,
) -> str:
    """Atalho para :meth:`DoughnutChart.render`."""
    return DoughnutChart(dataset, config=config).render()
