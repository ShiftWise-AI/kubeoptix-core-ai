"""Renderização de visualizações no relatório Markdown."""

from __future__ import annotations

import base64
import re
from pathlib import Path

from kubeoptix_core_ai.visualization.models import VisualizationSpec, VisualizationStatus
from kubeoptix_core_ai.visualization.png.export_config import (
    PROPOSED_NAMESPACE_VIZ_PREFIX,
    WIDE_DIAGRAM_VIZ_IDS,
)

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)(?:\{[^}]*\})?")
_HTML_IMG_RE = re.compile(
    r'(<img\s[^>]*src=")([^"]+)("[^>]*>)',
    re.IGNORECASE,
)


def _normalize_image_path(image_relpath: str) -> str:
    path = image_relpath
    if not path.startswith(("./", "../", "http://", "https://", "data:")):
        path = f"./{path}"
    return path


def _markdown_image(title: str, image_relpath: str) -> str:
    alt = title.replace("[", "").replace("]", "")
    return f"![{alt}]({_normalize_image_path(image_relpath)})"


def _markdown_architecture_image(title: str, image_relpath: str) -> str:
    """Imagem em largura de página para diagramas paisagem (arquitetura/placement)."""
    alt = title.replace("[", "").replace("]", "").replace('"', "")
    path = _normalize_image_path(image_relpath)
    return (
        f'<img src="{path}" alt="{alt}" '
        f'style="width:100%;max-width:100%;height:auto;" />'
    )


def embed_markdown_images(content: str, *, markdown_dir: Path) -> str:
    """Substitui referências PNG locais por data URIs embutidas no Markdown."""

    def _encode(ref: str) -> str | None:
        if ref.startswith(("http://", "https://", "data:")):
            return None
        normalized = ref.removeprefix("./")
        image_path = (markdown_dir / normalized).resolve()
        if not image_path.is_file():
            return None
        encoded = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _replace_md(match: re.Match[str]) -> str:
        alt, ref = match.group(1), match.group(2).strip()
        data_uri = _encode(ref)
        if data_uri is None:
            return match.group(0)
        return f"![{alt}]({data_uri})"

    def _replace_html(match: re.Match[str]) -> str:
        prefix, ref, suffix = match.group(1), match.group(2).strip(), match.group(3)
        data_uri = _encode(ref)
        if data_uri is None:
            return match.group(0)
        return f"{prefix}{data_uri}{suffix}"

    embedded = _MD_IMAGE_RE.sub(_replace_md, content)
    return _HTML_IMG_RE.sub(_replace_html, embedded)


def render_visualization_block(viz: VisualizationSpec) -> str:
    """Formata uma visualização como seção Markdown com imagem PNG."""
    lines = [f"### {viz.title}", "", f"*{viz.question}*", ""]

    if viz.interpretation:
        lines.append(viz.interpretation)
        lines.append("")

    if viz.status == VisualizationStatus.UNAVAILABLE:
        reason = viz.unavailable_reason or "Dados insuficientes."
        lines.append(f"_Visualização indisponível: {reason}_")
        lines.append("")
        return "\n".join(lines)

    if viz.image_relpath:
        if viz.diagram_engine == "kubediagrams":
            lines.append(
                "_Diagrama gerado a partir dos manifests YAML listados abaixo. "
                "Cores: Workloads (azul), Pods (azul-claro), Configuration (cinza), "
                "Storage (âmbar), Networking (verde), Nodes (lilás). "
                "Leitura em faixas horizontais (paisagem, largura de página): "
                "Workloads, Configuration, Storage, Networking, Nodes. "
                "Pods equivalentes são agrupados com o rótulo `nome (N replicas)`. "
                "Services exibem a porta (`nome:8000`)._"
            )
            lines.append("")
        if viz.yaml_sources:
            lines.append("**Manifests YAML utilizados:**")
            for source in viz.yaml_sources[:10]:
                lines.append(f"- `{source}`")
            if len(viz.yaml_sources) > 10:
                lines.append(f"- _… e mais {len(viz.yaml_sources) - 10} arquivo(s)_")
            lines.append("")
        if viz.id in WIDE_DIAGRAM_VIZ_IDS or viz.id.startswith(PROPOSED_NAMESPACE_VIZ_PREFIX):
            lines.extend([_markdown_architecture_image(viz.title, viz.image_relpath), ""])
        else:
            lines.extend([_markdown_image(viz.title, viz.image_relpath), ""])

    return "\n".join(lines)


def render_section_visualizations(visualizations: tuple[VisualizationSpec, ...]) -> str:
    if not visualizations:
        return ""
    blocks = [render_visualization_block(v) for v in visualizations]
    return "\n".join(blocks)
