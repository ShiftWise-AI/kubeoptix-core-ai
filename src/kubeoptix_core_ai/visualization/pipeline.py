"""Orquestração da geração de visualizações."""

from __future__ import annotations

from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.builders import build_all_visualizations
from kubeoptix_core_ai.visualization.models import VisualizationBundle


class VisualizationPipeline:
    """Produz visualizações Mermaid a partir de um AssessmentBundle."""

    def build(self, bundle: AssessmentBundle) -> VisualizationBundle:
        return build_all_visualizations(bundle)
