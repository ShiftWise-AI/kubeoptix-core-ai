"""Paleta e utilitários compartilhados entre gráficos HTML do projeto."""

from __future__ import annotations

import hashlib
import html

CHART_COLORS: tuple[str, ...] = (
    "#4472C4",
    "#ED7D31",
    "#70AD47",
    "#5B9BD5",
    "#A5A5A5",
    "#FFC000",
    "#264478",
    "#9E480E",
    "#43682B",
    "#255E91",
    "#997300",
    "#636363",
)

CHART_FONT = "system-ui,-apple-system,sans-serif"
CHART_TEXT_COLOR = "#151515"
CHART_MUTED_COLOR = "#666666"
CHART_AXIS_COLOR = "#D9D9D9"

CHART_MAX_WIDTH = 720
CHART_LEGEND_MIN_WIDTH = 200
CHART_GAP = 24
CHART_FONT_SIZE = 14
CHART_LABEL_FONT_SIZE = 11
CHART_RESPONSIVE_BREAKPOINT = 640
CHART_HOVER_OPACITY = 0.82


def format_chart_value(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


def format_chart_percent(value: float, total: float) -> str:
    if total <= 0:
        return "0%"
    pct = (value / total) * 100
    if pct == int(pct):
        return f"{int(pct)}%"
    return f"{pct:.1f}%"


def truncate_chart_label(label: str, max_len: int) -> str:
    if len(label) <= max_len:
        return label
    return f"{label[: max_len - 1]}…"


def build_chart_id(prefix: str, title: str, fingerprint: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in title.lower())
    slug = slug.strip("-") or "chart"
    digest = hashlib.sha1(f"{title}|{fingerprint}".encode()).hexdigest()[:8]
    return f"kubeoptix-{prefix}-{slug}-{digest}"


def legend_marker(color: str, *, circular: bool = False) -> str:
    radius = "50%" if circular else "2px"
    return (
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:{radius};'
        f"margin-top:4px;background:{color};flex-shrink:0;\"></span>"
    )


def legend_item(color: str, text: str, tooltip: str, *, circular: bool = False) -> str:
    marker = legend_marker(color, circular=circular)
    tooltip_esc = html.escape(tooltip)
    return (
        "<li "
        'style="display:flex;align-items:flex-start;gap:8px;line-height:1.35;" '
        f'title="{tooltip_esc}">'
        f"{marker}"
        f"<span>{text}</span>"
        "</li>"
    )


def chart_styles(chart_id: str, segment_class: str) -> str:
    return (
        f"<style>\n"
        f"#{chart_id} .{segment_class}:hover "
        f"{{ opacity: {CHART_HOVER_OPACITY}; cursor: help; }}\n"
        f"@media (max-width: {CHART_RESPONSIVE_BREAKPOINT}px) {{\n"
        f"  #{chart_id} {{ flex-direction: column; align-items: flex-start; }}\n"
        f"}}\n"
        f"</style>"
    )


def chart_container_open(
    chart_id: str,
    css_class: str,
    title: str,
    *,
    segment_class: str,
    max_width: int = CHART_MAX_WIDTH,
) -> str:
    title_esc = html.escape(title)
    return (
        f'<div class="{css_class}" id="{chart_id}" role="img" aria-label="{title_esc}" '
        f'style="display:flex;flex-wrap:wrap;align-items:center;gap:{CHART_GAP}px;'
        f"max-width:{max_width}px;font-family:{CHART_FONT};font-size:{CHART_FONT_SIZE}px;"
        f'color:{CHART_TEXT_COLOR};">'
        f"{chart_styles(chart_id, segment_class)}"
    )


def chart_plot_open() -> str:
    return '<div style="flex-shrink:0;overflow-x:auto;">'


def chart_plot_close() -> str:
    return "</div>"


def chart_legend_open(min_width: int = CHART_LEGEND_MIN_WIDTH) -> str:
    return (
        f'<ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;'
        f"gap:10px;min-width:{min_width}px;flex:1;\">"
    )


def chart_legend_close() -> str:
    return "</ul></div>"


def chart_empty_state(css_class: str, title: str) -> str:
    title_esc = html.escape(title or "Sem dados")
    return (
        f'<div class="{css_class} {css_class}--empty" role="img" aria-label="{title_esc}" '
        f'style="font-family:{CHART_FONT};font-size:{CHART_FONT_SIZE}px;'
        f'color:{CHART_MUTED_COLOR};">Sem dados para exibir.</div>'
    )
