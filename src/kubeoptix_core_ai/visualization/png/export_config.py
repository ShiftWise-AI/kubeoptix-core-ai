"""Parâmetros de exportação PNG para relatórios Markdown → PDF."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from kubeoptix_core_ai.visualization.chart_theme import CHART_MAX_WIDTH

LayoutProfile = Literal["chart", "diagram", "architecture"]

NAMESPACE_ARCHITECTURE_VIZ_ID = "namespace_architecture"

# Gráficos matplotlib: compactos para edição do Markdown.
REPORT_IMAGE_DPI = 120
REPORT_CHART_MAX_WIDTH_PX = CHART_MAX_WIDTH
REPORT_CHART_MAX_HEIGHT_PX = 420

# Diagramas de comunicação/workload: horizontais e moderados.
REPORT_DIAGRAM_MAX_WIDTH_PX = 960
REPORT_DIAGRAM_MAX_HEIGHT_PX = 540
REPORT_DIAGRAM_MIN_ASPECT_RATIO = 1.25

# Diagrama de arquitetura do namespace: página inteira, alta legibilidade.
# Largura útil A4 (~166 mm) ≈ 6,625 pol. a 200 dpi → ~1325 px.
REPORT_ARCHITECTURE_DPI = 200
REPORT_ARCHITECTURE_PAGE_WIDTH_IN = 6.625
REPORT_ARCHITECTURE_MAX_WIDTH_PX = 1320
REPORT_ARCHITECTURE_MAX_HEIGHT_PX = 960
REPORT_ARCHITECTURE_TARGET_WIDTH_PX = 1320
REPORT_ARCHITECTURE_MAX_UPSCALE = 1.35

EMPTY_CHART_FIGSIZE = (5.0, 2.5)
COMPOSITION_FIGSIZE = (6.5, 3.75)
NUMERIC_FIGSIZE_HEIGHT = 3.5


def layout_profile_for_viz(viz_id: str) -> LayoutProfile:
    if viz_id == NAMESPACE_ARCHITECTURE_VIZ_ID:
        return "architecture"
    return "diagram"


def layout_profile_for_output(output_path: Path) -> LayoutProfile:
    return layout_profile_for_viz(output_path.stem)


def numeric_figsize_width(label_count: int) -> float:
    """Largura da figura em polegadas conforme número de categorias."""
    return max(5.5, min(9.0, 3.2 + label_count * 0.55))


def flowchart_figsize(x_extent: float, y_extent: float) -> tuple[float, float]:
    """Dimensões dinâmicas para flowcharts matplotlib (fallback/testes)."""
    width = max(8.0, min(16.0, x_extent * 1.0))
    height = max(3.0, min(7.0, y_extent + 1.0))
    if width / height < REPORT_DIAGRAM_MIN_ASPECT_RATIO:
        height = width / REPORT_DIAGRAM_MIN_ASPECT_RATIO
    return width, height
