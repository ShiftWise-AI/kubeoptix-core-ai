"""Renderização unificada de diagramas: KubeDiagrams (padrão) + matplotlib (fallback)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from kubeoptix_core_ai.visualization.kubediagrams.manifest_index import ManifestIndex
from kubeoptix_core_ai.visualization.kubediagrams.renderer import KubeDiagramsRenderer
from kubeoptix_core_ai.visualization.models import FlowchartDataset
from kubeoptix_core_ai.visualization.png import PngRenderer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiagramRenderResult:
    image_relpath: str | None
    engine: str | None
    yaml_sources: tuple[str, ...] = ()
    failure_reason: str | None = None


class DiagramRenderer:
    """Renderiza diagramas de arquitetura/comunicação exclusivamente via KubeDiagrams."""

    def __init__(
        self,
        kubediagrams: KubeDiagramsRenderer,
        matplotlib: PngRenderer,
        *,
        manifest_index: ManifestIndex,
    ) -> None:
        self._kubediagrams = kubediagrams
        self._matplotlib = matplotlib
        self._index = manifest_index

    def render_flowchart(
        self,
        viz_id: str,
        manifests: tuple[Path, ...],
        fallback_dataset: FlowchartDataset | None = None,
    ) -> DiagramRenderResult:
        yaml_sources = self._index.relative_sources(manifests) if manifests else ()

        if manifests:
            image_path = self._kubediagrams.render_manifests(viz_id, manifests)
            if image_path is not None:
                return DiagramRenderResult(
                    image_relpath=image_path,
                    engine="kubediagrams",
                    yaml_sources=yaml_sources,
                )
            reason = self._kubediagrams.last_error
            logger.info(
                "KubeDiagrams indisponível ou falhou para %s; diagrama não será renderizado. Motivo: %s",
                viz_id,
                reason or "(não informado)",
            )
            return DiagramRenderResult(
                image_relpath=None,
                engine=None,
                yaml_sources=yaml_sources,
                failure_reason=reason,
            )

        # Regra de produto: diagramas de arquitetura/comunicação não devem usar
        # estilo alternativo; apenas KubeDiagrams é aceito para flowcharts.
        _ = fallback_dataset

        return DiagramRenderResult(image_relpath=None, engine=None, yaml_sources=yaml_sources)
