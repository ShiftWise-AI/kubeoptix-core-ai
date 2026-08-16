"""Inicialização de tema Mermaid para cores e preenchimento visíveis."""

from __future__ import annotations

# Paleta com contraste adequado em fundo branco (evita #ECECFF quase invisível).
_XY_PALETTE = "#4472C4, #ED7D31, #70AD47, #A5A5A5, #5B9BD5, #FFC000"

XYCHART_INIT = (
    "%%{init: {"
    '"themeVariables": {"xyChart": {"plotColorPalette": '
    f'"{_XY_PALETTE}"'
    "}}"
    "}}%%"
)

_PIE_COLORS = (
    '"pie1": "#4472C4", "pie2": "#ED7D31", "pie3": "#70AD47", '
    '"pie4": "#5B9BD5", "pie5": "#A5A5A5", "pie6": "#FFC000", '
    '"pie7": "#264478", "pie8": "#9E480E", "pie9": "#43682B", '
    '"pie10": "#255E91", "pie11": "#997300", "pie12": "#636363"'
)

PIE_INIT = f"%%{{init: {{\"themeVariables\": {{{_PIE_COLORS}}}}}}}%%"
