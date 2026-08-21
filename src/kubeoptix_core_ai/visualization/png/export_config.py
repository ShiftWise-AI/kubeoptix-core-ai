"""Parâmetros de exportação PNG para relatórios Markdown → PDF."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.chart_theme import CHART_MAX_WIDTH

# 120 dpi: nitidez suficiente para PDF A4/Letter sem arquivos pesados para edição.
REPORT_IMAGE_DPI = 120

# Alinhado ao max-width dos gráficos HTML e à largura útil típica de página PDF.
REPORT_CHART_MAX_WIDTH_PX = CHART_MAX_WIDTH
REPORT_CHART_MAX_HEIGHT_PX = 420

# Diagramas de arquitetura/comunicação exigem mais área horizontal.
REPORT_DIAGRAM_MAX_WIDTH_PX = 900
REPORT_DIAGRAM_MAX_HEIGHT_PX = 620

EMPTY_CHART_FIGSIZE = (5.0, 2.5)
COMPOSITION_FIGSIZE = (6.5, 3.75)
NUMERIC_FIGSIZE_HEIGHT = 3.5


def numeric_figsize_width(label_count: int) -> float:
    """Largura da figura em polegadas conforme número de categorias."""
    return max(5.5, min(9.0, 3.2 + label_count * 0.55))


def flowchart_figsize(x_extent: float, y_extent: float) -> tuple[float, float]:
    """Dimensões dinâmicas para flowcharts matplotlib (fallback/testes)."""
    width = max(7.0, min(14.0, x_extent * 0.9))
    height = max(3.5, min(10.0, y_extent + 1.5))
    return width, height
