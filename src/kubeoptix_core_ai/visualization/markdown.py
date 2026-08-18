"""Renderização de visualizações no relatório Markdown."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.models import VisualizationSpec, VisualizationStatus


def render_visualization_block(viz: VisualizationSpec) -> str:
    """Formata uma visualização como seção Markdown com bloco Mermaid."""
    lines = [f"### {viz.title}", "", f"*{viz.question}*", ""]

    if viz.interpretation:
        lines.append(viz.interpretation)
        lines.append("")

    if viz.status == VisualizationStatus.UNAVAILABLE:
        reason = viz.unavailable_reason or "Dados insuficientes."
        lines.append(f"_Visualização indisponível: {reason}_")
        lines.append("")
        return "\n".join(lines)

    if viz.mermaid:
        lines.extend(["```mermaid", viz.mermaid, "```", ""])

    return "\n".join(lines)


def render_section_visualizations(visualizations: tuple[VisualizationSpec, ...]) -> str:
    if not visualizations:
        return ""
    blocks = [render_visualization_block(v) for v in visualizations]
    return "\n".join(blocks)
