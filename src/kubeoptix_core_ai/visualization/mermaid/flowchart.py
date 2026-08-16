"""Renderização de diagramas Mermaid (flowchart)."""

from __future__ import annotations

from kubeoptix_core_ai.visualization.models import FlowchartDataset
from kubeoptix_core_ai.visualization.sanitize import (
    label_needs_rect_node_shape,
    sanitize_mermaid_edge_label,
    sanitize_mermaid_id,
    sanitize_mermaid_label,
)


def _quoted_label(label: str) -> str:
    return f'"{sanitize_mermaid_label(label)}"'


def _node_shape(node_type: str, node_id: str, label: str) -> str:
    quoted = _quoted_label(label)
    if label_needs_rect_node_shape(label):
        return f"    {node_id}[{quoted}]"
    if node_type == "external":
        # Stadium — evita paralelogramo [/…/], frágil com barras no texto.
        return f"    {node_id}([{quoted}])"
    if node_type == "route":
        return f"    {node_id}{{{{{quoted}}}}}"
    if node_type in ("service", "database", "messaging"):
        return f"    {node_id}[({quoted})]"
    if node_type in ("secret", "node"):
        return f"    {node_id}[[{quoted}]]"
    return f"    {node_id}[{quoted}]"


def render_flowchart(dataset: FlowchartDataset) -> str:
    """Gera bloco ``flowchart`` a partir de um :class:`FlowchartDataset`."""
    if not dataset.nodes:
        return f'flowchart {dataset.direction}\n    empty["Sem dados"]'

    lines = [f"flowchart {dataset.direction}"]
    seen_ids: set[str] = set()
    for node in dataset.nodes:
        node_id = sanitize_mermaid_id(node.id)
        if node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        lines.append(_node_shape(node.node_type, node_id, node.label))

    for edge in dataset.edges:
        source = sanitize_mermaid_id(edge.source_id)
        target = sanitize_mermaid_id(edge.target_id)
        if edge.label:
            label = sanitize_mermaid_edge_label(edge.label)
            lines.append(f"    {source} -->|{label}| {target}")
        else:
            lines.append(f"    {source} --> {target}")

    return "\n".join(lines)
