"""Camada de visualização PNG para relatórios de assessment."""

from kubeoptix_core_ai.visualization.models import (
    VisualizationBundle,
    VisualizationSpec,
    VisualizationStatus,
)
from kubeoptix_core_ai.visualization.markdown import render_visualization_block

__all__ = [
    "VisualizationBundle",
    "VisualizationSpec",
    "VisualizationStatus",
    "render_visualization_block",
    "VisualizationPipeline",
]


def __getattr__(name: str):
    if name == "VisualizationPipeline":
        from kubeoptix_core_ai.visualization.pipeline import VisualizationPipeline

        return VisualizationPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
