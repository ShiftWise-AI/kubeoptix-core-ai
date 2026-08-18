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


def _render_nodes_flat(dataset: FlowchartDataset, lines: list[str]) -> set[str]:
    seen_ids: set[str] = set()
    for node in dataset.nodes:
        node_id = sanitize_mermaid_id(node.id)
        if node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        lines.append(_node_shape(node.node_type, node_id, node.label))
    return seen_ids


def _render_nodes_grouped(dataset: FlowchartDataset, lines: list[str]) -> set[str]:
    subgraph_titles = {sg.id: sg.title for sg in dataset.subgraphs}
    nodes_by_subgraph: dict[str, list] = {sg.id: [] for sg in dataset.subgraphs}
    ungrouped: list = []

    for node in dataset.nodes:
        if node.subgraph and node.subgraph in nodes_by_subgraph:
            nodes_by_subgraph[node.subgraph].append(node)
        else:
            ungrouped.append(node)

    seen_ids: set[str] = set()
    for subgraph_id, title in subgraph_titles.items():
        group_nodes = nodes_by_subgraph.get(subgraph_id, [])
        if not group_nodes:
            continue
        sg_id = sanitize_mermaid_id(subgraph_id)
        lines.append(f'    subgraph {sg_id}["{sanitize_mermaid_label(title)}"]')
        for node in group_nodes:
            node_id = sanitize_mermaid_id(node.id)
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            lines.append(_node_shape(node.node_type, node_id, node.label))
        lines.append("    end")

    for node in ungrouped:
        node_id = sanitize_mermaid_id(node.id)
        if node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        lines.append(_node_shape(node.node_type, node_id, node.label))

    return seen_ids


def render_flowchart(dataset: FlowchartDataset) -> str:
    """Gera bloco ``flowchart`` a partir de um :class:`FlowchartDataset`."""
    if not dataset.nodes:
        return f'flowchart {dataset.direction}\n    empty["Sem dados"]'

    lines = [f"flowchart {dataset.direction}"]
    if dataset.subgraphs:
        _render_nodes_grouped(dataset, lines)
    else:
        _render_nodes_flat(dataset, lines)

    for edge in dataset.edges:
        source = sanitize_mermaid_id(edge.source_id)
        target = sanitize_mermaid_id(edge.target_id)
        if edge.label:
            label = sanitize_mermaid_edge_label(edge.label)
            lines.append(f"    {source} -->|{label}| {target}")
        else:
            lines.append(f"    {source} --> {target}")

    return "\n".join(lines)
