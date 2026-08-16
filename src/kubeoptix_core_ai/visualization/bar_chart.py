"""Componente reutilizável de Bar Chart para comparação entre categorias."""

from __future__ import annotations

import html
from dataclasses import dataclass

from kubeoptix_core_ai.visualization.chart_theme import (
    CHART_AXIS_COLOR,
    CHART_COLORS,
    CHART_LABEL_FONT_SIZE,
    CHART_MUTED_COLOR,
    CHART_TEXT_COLOR,
    build_chart_id,
    chart_container_open,
    chart_empty_state,
    chart_legend_close,
    chart_legend_open,
    chart_plot_close,
    chart_plot_open,
    format_chart_value,
    legend_item,
    truncate_chart_label,
)
from kubeoptix_core_ai.visualization.models import ChartDataset, ChartPoint, ChartSeries


def _format_point(point: ChartPoint) -> str:
    value = format_chart_value(point.value)
    unit = point.unit.strip()
    return f"{value} {unit}".strip() if unit else value


def _bar_series(dataset: ChartDataset) -> tuple[ChartSeries, ...]:
    return tuple(series for series in dataset.series if series.series_type == "bar")


def _point_for(series: ChartSeries, label: str) -> ChartPoint | None:
    for point in series.points:
        if point.label == label:
            return point
    return None


def _compute_max_value(dataset: ChartDataset) -> float:
    if dataset.y_max is not None:
        return dataset.y_max
    max_val = 0.0
    for series in dataset.series:
        for point in series.points:
            max_val = max(max_val, point.value)
    if max_val <= 0:
        return 1.0
    return max_val * 1.1


@dataclass(frozen=True)
class _XLabelLayout:
    max_len: int
    rotate_deg: int
    margin_bottom: int


def _x_label_layout(labels: tuple[str, ...]) -> _XLabelLayout:
    count = len(labels)
    longest = max((len(label) for label in labels), default=0)

    if count <= 3 and longest <= 18:
        return _XLabelLayout(max_len=20, rotate_deg=0, margin_bottom=52)
    if count <= 5 and longest <= 14:
        return _XLabelLayout(max_len=16, rotate_deg=0, margin_bottom=52)
    if count <= 8 and longest <= 20:
        return _XLabelLayout(max_len=14, rotate_deg=-35, margin_bottom=72)
    return _XLabelLayout(max_len=12, rotate_deg=-45, margin_bottom=84)


@dataclass(frozen=True)
class BarChartConfig:
    """Opções visuais compartilhadas por todos os Bar Charts do projeto."""

    colors: tuple[str, ...] = CHART_COLORS
    plot_height: int = 240
    plot_width: int = 360
    bar_width: int = 18
    series_gap: int = 4
    group_gap: int = 16
    margin_left: int = 56
    margin_top: int = 12
    legend_min_width: int = 200


class BarChart:
    """Renderiza barras verticais com legenda lateral e tooltip nativo."""

    _SEGMENT_CLASS = "kubeoptix-bar-segment"
    _CSS_CLASS = "kubeoptix-bar-chart"

    def __init__(
        self,
        dataset: ChartDataset,
        config: BarChartConfig | None = None,
    ) -> None:
        self.dataset = dataset
        self.config = config or BarChartConfig()

    def render(self) -> str:
        bars = _bar_series(self.dataset)
        if not self.dataset.x_labels or not bars:
            return chart_empty_state(self._CSS_CLASS, self.dataset.title)

        if len(bars) == 1 and len(self.dataset.series) == 1:
            return self._render_single_series(bars[0])
        return self._render_multi_series(bars)

    def _plot_metrics(self, num_groups: int, bars_per_group: int) -> tuple[int, float, float, float]:
        cfg = self.config
        group_width = (
            bars_per_group * cfg.bar_width + max(0, bars_per_group - 1) * cfg.series_gap
        )
        content_width = max(
            cfg.plot_width,
            num_groups * group_width + max(0, num_groups - 1) * cfg.group_gap,
        )
        baseline_y = cfg.margin_top + cfg.plot_height
        origin_x = cfg.margin_left
        return content_width, baseline_y, origin_x, group_width

    def _render_single_series(self, series: ChartSeries) -> str:
        cfg = self.config
        max_value = _compute_max_value(self.dataset)
        entries: list[tuple[str, ChartPoint, str]] = []

        for index, label in enumerate(self.dataset.x_labels):
            point = _point_for(series, label)
            if point is None:
                continue
            color = cfg.colors[index % len(cfg.colors)]
            entries.append((label, point, color))

        if not entries:
            return chart_empty_state(self._CSS_CLASS, self.dataset.title)

        content_width, baseline_y, origin_x, group_width = self._plot_metrics(len(entries), 1)
        x_layout = _x_label_layout(tuple(label for label, _, _ in entries))
        return self._wrap(
            max_value=max_value,
            bars_svg=self._bars_single_series(entries, origin_x, group_width, baseline_y, max_value),
            legend_items=self._legend_single_series(entries),
            origin_x=origin_x,
            baseline_y=baseline_y,
            content_height=cfg.plot_height,
            content_width=content_width,
            x_ticks=[
                (origin_x + index * (group_width + cfg.group_gap) + cfg.bar_width / 2, label)
                for index, (label, _, _) in enumerate(entries)
            ],
            x_layout=x_layout,
        )

    def _bars_single_series(
        self,
        entries: list[tuple[str, ChartPoint, str]],
        origin_x: float,
        group_width: float,
        baseline_y: float,
        max_value: float,
    ) -> str:
        cfg = self.config
        bars: list[str] = []
        for index, (label, point, color) in enumerate(entries):
            x = origin_x + index * (group_width + cfg.group_gap)
            bar_height = 0 if max_value <= 0 else (point.value / max_value) * cfg.plot_height
            y = baseline_y - bar_height
            tooltip = html.escape(f"{label}: {_format_point(point)}")
            bars.append(
                f'<rect class="{self._SEGMENT_CLASS}" x="{x:.1f}" y="{y:.1f}" '
                f'width="{cfg.bar_width}" height="{bar_height:.1f}" rx="3" fill="{color}">'
                f"<title>{tooltip}</title></rect>"
            )
        return "".join(bars)

    def _legend_single_series(self, entries: list[tuple[str, ChartPoint, str]]) -> str:
        items: list[str] = []
        for label, point, color in entries:
            value_text = _format_point(point)
            tooltip = f"{label}: {value_text}"
            items.append(
                legend_item(
                    color,
                    f"{html.escape(label)} — {html.escape(value_text)}",
                    tooltip,
                )
            )
        return "".join(items)

    def _render_multi_series(self, bars: tuple[ChartSeries, ...]) -> str:
        cfg = self.config
        max_value = _compute_max_value(self.dataset)
        num_groups = len(self.dataset.x_labels)
        bars_per_group = len(bars)
        content_width, baseline_y, origin_x, group_width = self._plot_metrics(
            num_groups, bars_per_group
        )
        grouped_width = (
            bars_per_group * cfg.bar_width + max(0, bars_per_group - 1) * cfg.series_gap
        )
        x_layout = _x_label_layout(self.dataset.x_labels)
        legend_items: list[str] = []
        bars_svg: list[str] = []
        x_ticks: list[tuple[float, str]] = []

        for series_index, series in enumerate(bars):
            color = cfg.colors[series_index % len(cfg.colors)]
            legend_items.append(legend_item(color, html.escape(series.name), series.name))

        for group_index, label in enumerate(self.dataset.x_labels):
            group_x = origin_x + group_index * (grouped_width + cfg.group_gap)
            x_ticks.append((group_x + grouped_width / 2, label))
            for series_index, series in enumerate(bars):
                color = cfg.colors[series_index % len(cfg.colors)]
                point = _point_for(series, label)
                if point is None:
                    continue
                x = group_x + series_index * (cfg.bar_width + cfg.series_gap)
                bar_height = 0 if max_value <= 0 else (point.value / max_value) * cfg.plot_height
                y = baseline_y - bar_height
                value_text = _format_point(point)
                tooltip = html.escape(f"{label} · {series.name}: {value_text}")
                bars_svg.append(
                    f'<rect class="{self._SEGMENT_CLASS}" x="{x:.1f}" y="{y:.1f}" '
                    f'width="{cfg.bar_width}" height="{bar_height:.1f}" rx="3" fill="{color}">'
                    f"<title>{tooltip}</title></rect>"
                )

        return self._wrap(
            max_value=max_value,
            bars_svg="".join(bars_svg),
            legend_items="".join(legend_items),
            origin_x=origin_x,
            baseline_y=baseline_y,
            content_height=cfg.plot_height,
            content_width=content_width,
            x_ticks=x_ticks,
            x_layout=x_layout,
        )

    def _render_x_axis(
        self,
        *,
        origin_x: float,
        baseline_y: float,
        content_width: float,
        x_ticks: list[tuple[float, str]],
        x_axis_label: str,
        x_layout: _XLabelLayout,
    ) -> str:
        end_x = origin_x + content_width
        parts = [
            f'<line x1="{origin_x:.1f}" y1="{baseline_y:.1f}" x2="{end_x:.1f}" y2="{baseline_y:.1f}" '
            f'stroke="{CHART_AXIS_COLOR}" stroke-width="1"/>',
            f'<text x="{(origin_x + end_x) / 2:.1f}" y="{baseline_y + x_layout.margin_bottom - 6:.1f}" '
            f'font-size="{CHART_LABEL_FONT_SIZE}" fill="{CHART_MUTED_COLOR}" '
            f'text-anchor="middle">{x_axis_label}</text>',
        ]

        label_y = baseline_y + 16
        for center_x, label in x_ticks:
            short = html.escape(truncate_chart_label(label, x_layout.max_len))
            full = html.escape(label)
            parts.append(
                f'<line x1="{center_x:.1f}" y1="{baseline_y:.1f}" x2="{center_x:.1f}" '
                f'y2="{baseline_y + 4:.1f}" stroke="{CHART_AXIS_COLOR}" stroke-width="1"/>'
            )
            if x_layout.rotate_deg == 0:
                parts.append(
                    f'<text x="{center_x:.1f}" y="{label_y:.1f}" font-size="{CHART_LABEL_FONT_SIZE}" '
                    f'fill="{CHART_TEXT_COLOR}" text-anchor="middle">'
                    f"<title>{full}</title>{short}</text>"
                )
            else:
                parts.append(
                    f'<text x="{center_x:.1f}" y="{label_y:.1f}" font-size="{CHART_LABEL_FONT_SIZE}" '
                    f'fill="{CHART_TEXT_COLOR}" text-anchor="end" '
                    f'transform="rotate({x_layout.rotate_deg} {center_x:.1f} {label_y:.1f})">'
                    f"<title>{full}</title>{short}</text>"
                )

        return "".join(parts)

    def _render_y_axis(
        self,
        *,
        origin_x: float,
        baseline_y: float,
        content_height: float,
        y_axis_label: str,
        max_value: float,
    ) -> str:
        top_y = baseline_y - content_height
        axis_max = html.escape(format_chart_value(max_value))
        label_x = origin_x - 28
        label_y = (top_y + baseline_y) / 2
        return (
            f'<line x1="{origin_x:.1f}" y1="{top_y:.1f}" x2="{origin_x:.1f}" y2="{baseline_y:.1f}" '
            f'stroke="{CHART_AXIS_COLOR}" stroke-width="1"/>'
            f'<text x="{origin_x - 6:.1f}" y="{baseline_y - 2:.1f}" font-size="{CHART_LABEL_FONT_SIZE}" '
            f'fill="{CHART_MUTED_COLOR}" text-anchor="end">0</text>'
            f'<text x="{origin_x - 6:.1f}" y="{top_y + 10:.1f}" font-size="{CHART_LABEL_FONT_SIZE}" '
            f'fill="{CHART_MUTED_COLOR}" text-anchor="end">{axis_max}</text>'
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" font-size="{CHART_LABEL_FONT_SIZE}" '
            f'fill="{CHART_MUTED_COLOR}" text-anchor="middle" '
            f'transform="rotate(-90 {label_x:.1f} {label_y:.1f})">{y_axis_label}</text>'
        )

    def _wrap(
        self,
        *,
        max_value: float,
        bars_svg: str,
        legend_items: str,
        origin_x: float,
        baseline_y: float,
        content_height: float,
        content_width: float,
        x_ticks: list[tuple[float, str]],
        x_layout: _XLabelLayout,
    ) -> str:
        cfg = self.config
        chart_id = self._chart_id()
        svg_width = origin_x + content_width + 16
        svg_height = baseline_y + x_layout.margin_bottom
        y_axis = self._render_y_axis(
            origin_x=origin_x,
            baseline_y=baseline_y,
            content_height=content_height,
            y_axis_label=html.escape(self.dataset.y_axis_label),
            max_value=max_value,
        )
        x_axis = self._render_x_axis(
            origin_x=origin_x,
            baseline_y=baseline_y,
            content_width=content_width,
            x_ticks=x_ticks,
            x_axis_label=html.escape(self.dataset.x_axis_label),
            x_layout=x_layout,
        )
        parts = [
            chart_container_open(
                chart_id,
                self._CSS_CLASS,
                self.dataset.title,
                segment_class=self._SEGMENT_CLASS,
            ),
            chart_plot_open(),
            f'<svg viewBox="0 0 {svg_width} {svg_height}" width="{svg_width}" height="{svg_height}" aria-hidden="true">',
            "<g>",
            y_axis,
            x_axis,
            bars_svg,
            "</g>",
            "</svg>",
            chart_plot_close(),
            chart_legend_open(cfg.legend_min_width),
            legend_items,
            chart_legend_close(),
        ]
        return "".join(parts)

    def _chart_id(self) -> str:
        fingerprint = "|".join(
            f"{series.name}:{point.label}:{point.value}"
            for series in self.dataset.series
            for point in series.points
        )
        return build_chart_id("bar", self.dataset.title, fingerprint)


def render_bar_chart(
    dataset: ChartDataset,
    config: BarChartConfig | None = None,
) -> str:
    """Atalho para :meth:`BarChart.render`."""
    return BarChart(dataset, config=config).render()
