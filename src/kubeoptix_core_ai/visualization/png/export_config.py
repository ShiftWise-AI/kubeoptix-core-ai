"""Parâmetros de exportação PNG para relatórios Markdown → PDF."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.chart_theme import CHART_MAX_WIDTH

# 120 dpi: nitidez suficiente para PDF A4/Letter sem arquivos pesados para edição.
REPORT_IMAGE_DPI = 120

# Alinhado ao max-width dos gráficos HTML e à largura útil típica de página PDF.
REPORT_CHART_MAX_WIDTH_PX = CHART_MAX_WIDTH
REPORT_CHART_MAX_HEIGHT_PX = 420

# Diagramas horizontais: largura maior que altura para leitura em PDF.
REPORT_DIAGRAM_MAX_WIDTH_PX = 960
REPORT_DIAGRAM_MAX_HEIGHT_PX = 540
REPORT_DIAGRAM_MIN_ASPECT_RATIO = 1.25

EMPTY_CHART_FIGSIZE = (5.0, 2.5)
COMPOSITION_FIGSIZE = (6.5, 3.75)
NUMERIC_FIGSIZE_HEIGHT = 3.5


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
