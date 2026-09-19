"""Orquestração da geração de visualizações."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.builders import build_all_visualizations
from kubeoptix_core_ai.visualization.diagram_renderer import DiagramRenderer
from kubeoptix_core_ai.visualization.kubediagrams import KubeDiagramsRenderer, manifest_index_for
from kubeoptix_core_ai.visualization.models import VisualizationBundle
from kubeoptix_core_ai.visualization.png import PngRenderer


def report_assets_prefix(namespace: str) -> str:
    """Prefixo relativo da pasta de imagens no Markdown do relatório."""
    clean_namespace = namespace.removeprefix("ml-")
    return f"ml-{clean_namespace}_assets"


@dataclass(frozen=True)
class VisualizationRenderers:
    png: PngRenderer
    diagram: DiagramRenderer


def create_renderers(
    bundle: AssessmentBundle,
    assets_dir: Path,
    *,
    assets_prefix: str = "",
) -> VisualizationRenderers:
    """Cria renderizadores PNG (matplotlib) e diagramas (KubeDiagrams + fallback)."""
    png_renderer = PngRenderer(assets_dir, path_prefix=assets_prefix)
    index = manifest_index_for(bundle)
    kubediagrams = KubeDiagramsRenderer(
        assets_dir,
        namespace=bundle.analysis.namespace,
        path_prefix=assets_prefix,
    )
    diagram_renderer = DiagramRenderer(
        kubediagrams,
        png_renderer,
        manifest_index=index,
    )
    return VisualizationRenderers(png=png_renderer, diagram=diagram_renderer)


class VisualizationPipeline:
    """Produz visualizações PNG a partir de um AssessmentBundle."""

    def build(
        self,
        bundle: AssessmentBundle,
        *,
        assets_dir: Path | None = None,
        assets_prefix: str = "",
        renderers: VisualizationRenderers | None = None,
    ) -> VisualizationBundle:
        if renderers is not None:
            return build_all_visualizations(
                bundle,
                renderer=renderers.png,
                diagram_renderer=renderers.diagram,
            )
        if assets_dir is None:
            return build_all_visualizations(bundle)
        built = create_renderers(bundle, assets_dir, assets_prefix=assets_prefix)
        return build_all_visualizations(
            bundle,
            renderer=built.png,
            diagram_renderer=built.diagram,
        )
