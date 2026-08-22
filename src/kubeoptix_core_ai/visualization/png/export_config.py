"""Parâmetros de exportação PNG para relatórios Markdown → PDF."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from kubeoptix_core_ai.visualization.chart_theme import CHART_MAX_WIDTH

LayoutProfile = Literal["chart", "diagram", "architecture"]

NAMESPACE_ARCHITECTURE_VIZ_ID = "namespace_architecture"
PROPOSED_NAMESPACE_VIZ_PREFIX = "proposed_ns_"
WORKLOAD_NODE_PLACEMENT_VIZ_ID = "workload_node_placement"
WIDE_DIAGRAM_VIZ_IDS = frozenset(
    {NAMESPACE_ARCHITECTURE_VIZ_ID, WORKLOAD_NODE_PLACEMENT_VIZ_ID}
)

# Gráficos matplotlib: compactos para edição do Markdown.
REPORT_IMAGE_DPI = 120
REPORT_CHART_MAX_WIDTH_PX = CHART_MAX_WIDTH
REPORT_CHART_MAX_HEIGHT_PX = 420

# Diagramas de comunicação/workload: horizontais e moderados.
REPORT_DIAGRAM_MAX_WIDTH_PX = 960
REPORT_DIAGRAM_MAX_HEIGHT_PX = 540
REPORT_DIAGRAM_MIN_ASPECT_RATIO = 1.25

# Arquitetura e placement: paisagem em largura de página (A4 landscape ~160 mm).
# size Graphviz em polegadas; dpi 120 evita PNGs gigantes ilegíveis ao reduzir.
REPORT_ARCHITECTURE_DPI = 120
REPORT_ARCHITECTURE_PAGE_WIDTH_IN = 16.0
REPORT_ARCHITECTURE_PAGE_HEIGHT_IN = 6.5
REPORT_ARCHITECTURE_MAX_WIDTH_PX = 1600
REPORT_ARCHITECTURE_MAX_HEIGHT_PX = 720
REPORT_ARCHITECTURE_TARGET_WIDTH_PX = 1600
REPORT_ARCHITECTURE_MAX_UPSCALE = 2.5
REPORT_ARCHITECTURE_MIN_ASPECT_RATIO = 1.6

EMPTY_CHART_FIGSIZE = (5.0, 2.5)
COMPOSITION_FIGSIZE = (6.5, 3.75)
NUMERIC_FIGSIZE_HEIGHT = 3.5


def layout_profile_for_viz(viz_id: str) -> LayoutProfile:
    if viz_id in WIDE_DIAGRAM_VIZ_IDS or viz_id.startswith(PROPOSED_NAMESPACE_VIZ_PREFIX):
        return "architecture"
    return "diagram"


def layout_profile_for_output(output_path: Path) -> LayoutProfile:
    return layout_profile_for_viz(output_path.stem)


def numeric_figsize_width(label_count: int) -> float:
    """Largura da figura em polegadas conforme número de categorias."""
    return max(5.5, min(9.0, 3.2 + label_count * 0.55))


def flowchart_figsize(x_extent: float, y_extent: float) -> tuple[float, float]:
    """Dimensões dinâmicas para flowcharts matplotlib (fallback/testes)."""
    width = max(10.0, min(16.0, x_extent * 0.95))
    height = max(3.2, min(6.5, y_extent + 0.8))
    if width / max(height, 0.1) < REPORT_ARCHITECTURE_MIN_ASPECT_RATIO:
        width = min(16.0, height * REPORT_ARCHITECTURE_MIN_ASPECT_RATIO)
    return width, height
