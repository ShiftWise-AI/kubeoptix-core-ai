"""Renderização de visualizações no relatório Markdown."""

from __future__ import annotations

import base64
import re
from pathlib import Path

from kubeoptix_core_ai.visualization.models import VisualizationSpec, VisualizationStatus

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)(\{[^}]*\})?")


def _normalize_image_path(image_relpath: str) -> str:
    path = image_relpath
    if not path.startswith(("./", "../", "http://", "https://", "data:")):
        path = f"./{path}"
    return path


def _markdown_image(title: str, image_relpath: str) -> str:
    alt = title.replace("[", "").replace("]", "")
    return f"![{alt}]({_normalize_image_path(image_relpath)})"


def _markdown_architecture_image(title: str, image_relpath: str) -> str:
    """Imagem de arquitetura em largura total de página (Pandoc/LaTeX)."""
    alt = title.replace("[", "").replace("]", "")
    return f"![{alt}]({_normalize_image_path(image_relpath)}){{ width=100% }}"


def embed_markdown_images(content: str, *, markdown_dir: Path) -> str:
    """Substitui referências PNG locais por data URIs embutidas no Markdown."""

    def _replace(match: re.Match[str]) -> str:
        alt, ref = match.group(1), match.group(2).strip()
        attrs = match.group(3) or ""
        if ref.startswith(("http://", "https://", "data:")):
            return match.group(0)
        normalized = ref.removeprefix("./")
        image_path = (markdown_dir / normalized).resolve()
        if not image_path.is_file():
            return match.group(0)
        encoded = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
        return f"![{alt}](data:image/png;base64,{encoded}){attrs}"

    return _MD_IMAGE_RE.sub(_replace, content)


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
                "Storage (âmbar), Networking (verde). "
                "Leitura horizontal: Workloads → Configuration → Storage → Networking. "
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
        lines.extend([_markdown_image(viz.title, viz.image_relpath), ""])

    return "\n".join(lines)


def render_section_visualizations(visualizations: tuple[VisualizationSpec, ...]) -> str:
    if not visualizations:
        return ""
    blocks = [render_visualization_block(v) for v in visualizations]
    return "\n".join(blocks)
