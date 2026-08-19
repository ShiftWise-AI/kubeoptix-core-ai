"""Renderização de datasets em imagens PNG (matplotlib)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.visualization.models import (
    ChartDataset,
    CompositionDataset,
    FlowchartDataset,
)
from kubeoptix_core_ai.visualization.png.assets import safe_asset_filename
from kubeoptix_core_ai.visualization.png.composition import render_composition_png
from kubeoptix_core_ai.visualization.png.flowchart import render_flowchart_png
from kubeoptix_core_ai.visualization.png.numeric import render_numeric_png


class PngRenderer:
    """Grava visualizações como PNG e retorna caminhos relativos para o Markdown."""

    def __init__(self, assets_dir: Path, *, path_prefix: str = "") -> None:
        self._assets_dir = assets_dir
        self._path_prefix = path_prefix.strip("/")
        self._assets_dir.mkdir(parents=True, exist_ok=True)

    def _relative_path(self, viz_id: str) -> str:
        filename = safe_asset_filename(viz_id)
        if self._path_prefix:
            return f"{self._path_prefix}/{filename}"
        return filename

    def _output_path(self, viz_id: str) -> Path:
        return self._assets_dir / safe_asset_filename(viz_id)

    def render_numeric(self, viz_id: str, dataset: ChartDataset) -> str:
        render_numeric_png(dataset, self._output_path(viz_id))
        return self._relative_path(viz_id)

    def render_composition(self, viz_id: str, dataset: CompositionDataset) -> str:
        render_composition_png(dataset, self._output_path(viz_id))
        return self._relative_path(viz_id)

    def render_flowchart(self, viz_id: str, dataset: FlowchartDataset) -> str:
        render_flowchart_png(dataset, self._output_path(viz_id))
        return self._relative_path(viz_id)
