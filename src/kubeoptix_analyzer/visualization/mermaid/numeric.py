"""Renderização de gráficos numéricos Mermaid (xychart-beta)."""

from __future__ import annotations

from kubeoptix_analyzer.visualization.mermaid.theme import XYCHART_INIT
from kubeoptix_analyzer.visualization.models import ChartDataset
from kubeoptix_analyzer.visualization.sanitize import sanitize_mermaid_label


def _quoted_label(label: str) -> str:
    return f'"{sanitize_mermaid_label(label)}"'


def _format_values(values: tuple[float, ...]) -> str:
    formatted: list[str] = []
    for value in values:
        if value == int(value):
            formatted.append(str(int(value)))
        else:
            formatted.append(f"{value:.2f}")
    return ", ".join(formatted)


def _compute_y_max(dataset: ChartDataset) -> float:
    if dataset.y_max is not None:
        return dataset.y_max
    max_val = 0.0
    for series in dataset.series:
        for point in series.points:
            max_val = max(max_val, point.value)
    if max_val <= 0:
        return 1.0
    return max_val * 1.1


def _format_y_max(value: float) -> str:
    if abs(value - round(value)) < 0.01:
        return str(int(round(value)))
    return f"{value:.2f}"


def render_xy_chart(dataset: ChartDataset) -> str:
    """Gera bloco ``xychart-beta`` a partir de um :class:`ChartDataset`."""
    if not dataset.x_labels or not dataset.series:
        return f"{XYCHART_INIT}\nxychart-beta\n    title \"Sem dados\""

    y_max = _format_y_max(_compute_y_max(dataset))
    title = sanitize_mermaid_label(dataset.title)
    y_label = sanitize_mermaid_label(dataset.y_axis_label)
    x_labels = ", ".join(_quoted_label(label) for label in dataset.x_labels)

    lines = [
        XYCHART_INIT,
        "xychart-beta",
        f'    title "{title}"',
        f"    x-axis [{x_labels}]",
        f'    y-axis "{y_label}" 0 --> {y_max}',
    ]

    for series in dataset.series:
        values = tuple(
            next((p.value for p in series.points if p.label == label), 0.0)
            for label in dataset.x_labels
        )
        values_str = _format_values(values)
        series_name = sanitize_mermaid_label(series.name)
        if series.series_type == "line":
            lines.append(f'    line "{series_name}" [{values_str}]')
        else:
            lines.append(f'    bar "{series_name}" [{values_str}]')

    return "\n".join(lines)
