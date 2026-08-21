"""Configuração compartilhada do matplotlib (backend headless)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from kubeoptix_core_ai.visualization.png.postprocess import optimize_png_canvas

DEFAULT_FIGURE_DPI = 150
DEFAULT_PAD_INCHES = 0.02


def save_figure(fig, output_path: Path, *, dpi: int = DEFAULT_FIGURE_DPI) -> None:
    """Exporta figura matplotlib com margens mínimas e normaliza o canvas PNG."""
    fig.savefig(
        output_path,
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=DEFAULT_PAD_INCHES,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    optimize_png_canvas(output_path)
