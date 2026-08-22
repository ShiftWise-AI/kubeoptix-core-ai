"""Diagramas de fluxo em PNG (matplotlib)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

from kubeoptix_core_ai.visualization.chart_theme import CHART_MUTED_COLOR
from kubeoptix_core_ai.visualization.models import DiagramEdge, DiagramNode, FlowchartDataset
from kubeoptix_core_ai.visualization.png._mpl import matplotlib, save_figure  # noqa: F401
from kubeoptix_core_ai.visualization.png.export_config import EMPTY_CHART_FIGSIZE, flowchart_figsize, layout_profile_for_output

import matplotlib.pyplot as plt

# Paleta D — corporativa Red Hat (vermelho, preto, cinzas, navy).
_NODE_STYLE: dict[str, dict[str, str | float]] = {
    "external": {"facecolor": "#D6E4F0", "edgecolor": "#002F5D", "boxstyle": "round,pad=0.35"},
    "route": {"facecolor": "#F5D0CD", "edgecolor": "#C9190B"},
    "service": {"facecolor": "#E8E8E8", "edgecolor": "#4D4D4D", "boxstyle": "round,pad=0.25"},
    "database": {"facecolor": "#D6E4F0", "edgecolor": "#002F5D", "boxstyle": "round,pad=0.25"},
    "messaging": {"facecolor": "#E8E8E8", "edgecolor": "#6A6E73", "boxstyle": "round,pad=0.25"},
    "secret": {"facecolor": "#F0F0F0", "edgecolor": "#151515", "linewidth": 2.0},
    "node": {"facecolor": "#F0F0F0", "edgecolor": "#151515", "linewidth": 2.0},
    "workload": {"facecolor": "#FFFFFF", "edgecolor": "#C9190B", "boxstyle": "round,pad=0.2"},
    "pod": {"facecolor": "#FFFFFF", "edgecolor": "#4D4D4D", "boxstyle": "round,pad=0.2"},
}

_DEFAULT_STYLE = {"facecolor": "#FFFFFF", "edgecolor": "#151515", "boxstyle": "round,pad=0.2"}
_EDGE_COLOR = "#4D4D4D"
_EDGE_LABEL_COLOR = "#4D4D4D"
_CLUSTER_FACE = "#FAFAFA"
_CLUSTER_EDGE = "#D2D2D2"
_CLUSTER_TITLE = "#4D4D4D"
_MAX_NODES_PER_COLUMN = 4


@dataclass(frozen=True)
class _NodeLayout:
    node: DiagramNode
    x: float
    y: float
    width: float
    height: float


def _estimate_size(label: str) -> tuple[float, float]:
    lines = label.split("\n")
    width = max(1.8, min(4.5, 0.12 * max(len(line) for line in lines) + 1.0))
    height = max(0.55, 0.35 * len(lines) + 0.35)
    return width, height


def _layer_nodes(nodes: tuple[DiagramNode, ...], edges: tuple[DiagramEdge, ...]) -> dict[str, int]:
    node_ids = [node.id for node in nodes]
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.source_id in indegree and edge.target_id in indegree:
            adjacency[edge.source_id].append(edge.target_id)
            indegree[edge.target_id] += 1

    layers: dict[str, int] = {}
    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    if not queue:
        queue = deque(node_ids[:1])

    while queue:
        current = queue.popleft()
        current_layer = layers.get(current, 0)
        for target in adjacency.get(current, []):
            layers[target] = max(layers.get(target, 0), current_layer + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    for index, node_id in enumerate(node_ids):
        layers.setdefault(node_id, index % 3)
    return layers


def _group_nodes(dataset: FlowchartDataset) -> list[tuple[str | None, tuple[DiagramNode, ...]]]:
    if not dataset.subgraphs:
        return [(None, dataset.nodes)]

    subgraph_order = [sg.id for sg in dataset.subgraphs]
    title_by_id = {sg.id: sg.title for sg in dataset.subgraphs}
    grouped: dict[str | None, list[DiagramNode]] = {sg_id: [] for sg_id in subgraph_order}
    ungrouped: list[DiagramNode] = []

    for node in dataset.nodes:
        if node.subgraph and node.subgraph in grouped:
            grouped[node.subgraph].append(node)
        else:
            ungrouped.append(node)

    result: list[tuple[str | None, tuple[DiagramNode, ...]]] = []
    for sg_id in subgraph_order:
        nodes = tuple(grouped.get(sg_id, []))
        if nodes:
            result.append((title_by_id.get(sg_id, sg_id), nodes))
    if ungrouped:
        result.append((None, tuple(ungrouped)))
    return result


def _layout_group(
    nodes: tuple[DiagramNode, ...],
    edges: tuple[DiagramEdge, ...],
    *,
    start_x: float,
    direction: str,
) -> tuple[list[_NodeLayout], float, float]:
    node_ids = {node.id for node in nodes}
    local_edges = tuple(
        edge
        for edge in edges
        if edge.source_id in node_ids and edge.target_id in node_ids
    )
    layers = _layer_nodes(nodes, local_edges)
    by_layer: dict[int, list[DiagramNode]] = defaultdict(list)
    for node in nodes:
        by_layer[layers.get(node.id, 0)].append(node)

    layouts: list[_NodeLayout] = []
    layer_gap = 1.4
    row_gap = 0.35
    max_height = 0.0
    max_extent = start_x

    if direction == "TB":
        y_cursor = 0.0
        for layer_index in sorted(by_layer):
            layer_nodes = by_layer[layer_index]
            row_width = 0.0
            row_height = 0.0
            for node in layer_nodes:
                width, height = _estimate_size(node.label)
                layouts.append(_NodeLayout(node=node, x=row_width, y=y_cursor, width=width, height=height))
                row_width += width + row_gap
                row_height = max(row_height, height)
            max_extent = max(max_extent, row_width)
            max_height = y_cursor + row_height
            y_cursor += row_height + layer_gap
        return layouts, max_extent, max_height

    x_cursor = start_x
    group_height = 0.0
    for layer_index in sorted(by_layer):
        layer_nodes = by_layer[layer_index]
        col_x = x_cursor
        col_y = 0.0
        col_width = 0.0
        stacked = 0
        layer_height = 0.0
        for node in layer_nodes:
            width, height = _estimate_size(node.label)
            if stacked >= _MAX_NODES_PER_COLUMN:
                col_x += col_width + 0.4
                col_y = 0.0
                col_width = 0.0
                stacked = 0
            layouts.append(
                _NodeLayout(node=node, x=col_x, y=-col_y, width=width, height=height)
            )
            col_y += height + row_gap
            col_width = max(col_width, width)
            stacked += 1
            layer_height = max(layer_height, col_y)
        group_height = max(group_height, layer_height)
        x_cursor = col_x + col_width + layer_gap
    return layouts, x_cursor, group_height


def _draw_node(ax: plt.Axes, layout: _NodeLayout) -> None:
    style = dict(_DEFAULT_STYLE)
    style.update(_NODE_STYLE.get(layout.node.node_type, {}))
    x, y = layout.x, layout.y
    width, height = layout.width, layout.height

    if layout.node.node_type == "route":
        diamond = Polygon(
            [
                (x + width / 2, y),
                (x + width, y + height / 2),
                (x + width / 2, y + height),
                (x, y + height / 2),
            ],
            closed=True,
            facecolor=str(style.get("facecolor", "#F5D0CD")),
            edgecolor=str(style.get("edgecolor", "#C9190B")),
            linewidth=float(style.get("linewidth", 1.2)),
        )
        ax.add_patch(diamond)
    else:
        boxstyle = str(style.get("boxstyle", "round,pad=0.2"))
        patch = FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle=boxstyle,
            facecolor=str(style.get("facecolor", "#FFFFFF")),
            edgecolor=str(style.get("edgecolor", "#151515")),
            linewidth=float(style.get("linewidth", 1.2)),
        )
        ax.add_patch(patch)
        if layout.node.node_type in ("secret", "node"):
            inner = FancyBboxPatch(
                (x + 0.06, y + 0.06),
                width - 0.12,
                height - 0.12,
                boxstyle=boxstyle,
                facecolor="none",
                edgecolor=str(style.get("edgecolor", "#151515")),
                linewidth=0.8,
            )
            ax.add_patch(inner)

    ax.text(
        x + width / 2,
        y + height / 2,
        layout.node.label,
        ha="center",
        va="center",
        fontsize=9,
        wrap=True,
    )


def _node_center(layout: _NodeLayout) -> tuple[float, float]:
    return layout.x + layout.width / 2, layout.y + layout.height / 2


def _draw_edge(ax: plt.Axes, source: _NodeLayout, target: _NodeLayout, label: str | None) -> None:
    sx, sy = _node_center(source)
    tx, ty = _node_center(target)
    arrow = FancyArrowPatch(
        (sx, sy),
        (tx, ty),
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=1.0,
        color=_EDGE_COLOR,
        connectionstyle="arc3,rad=0.08",
    )
    ax.add_patch(arrow)
    if label:
        ax.text((sx + tx) / 2, (sy + ty) / 2, label, fontsize=6, ha="center", va="center", color=_EDGE_LABEL_COLOR)


def _empty_chart(output_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=EMPTY_CHART_FIGSIZE)
    ax.axis("off")
    ax.text(0.5, 0.5, "Sem dados para exibir", ha="center", va="center", fontsize=12, color=CHART_MUTED_COLOR)
    ax.set_title(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    save_figure(fig, output_path, profile=layout_profile_for_output(output_path))
    plt.close(fig)


def render_flowchart_png(dataset: FlowchartDataset, output_path: Path) -> None:
    """Gera PNG de flowchart a partir de um :class:`FlowchartDataset`."""
    if not dataset.nodes:
        _empty_chart(output_path, dataset.title)
        return

    direction = dataset.direction
    groups = _group_nodes(dataset)
    all_layouts: list[_NodeLayout] = []
    cluster_boxes: list[tuple[str | None, float, float, float, float]] = []
    x_cursor = 0.5
    y_top = 0.0

    for title, nodes in groups:
        group_layouts, group_width, group_height = _layout_group(
            nodes,
            dataset.edges,
            start_x=x_cursor,
            direction=direction,
        )
        if not group_layouts:
            continue
        min_x = min(layout.x for layout in group_layouts)
        min_y = min(layout.y for layout in group_layouts)
        max_x = max(layout.x + layout.width for layout in group_layouts)
        max_y = max(layout.y + layout.height for layout in group_layouts)
        cluster_boxes.append((title, min_x - 0.25, min_y - 0.25, max_x + 0.25, max_y + 0.25))
        all_layouts.extend(group_layouts)
        x_cursor = max_x + 1.2
        y_top = max(y_top, max_y)

    layout_by_id = {layout.node.id: layout for layout in all_layouts}
    fig_width, fig_height = flowchart_figsize(x_cursor, y_top + 2)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    for title, min_x, min_y, max_x, max_y in cluster_boxes:
        if title:
            cluster = FancyBboxPatch(
                (min_x, min_y),
                max_x - min_x,
                max_y - min_y,
                boxstyle="round,pad=0.15",
                facecolor=_CLUSTER_FACE,
                edgecolor=_CLUSTER_EDGE,
                linewidth=1.0,
                linestyle="--",
            )
            ax.add_patch(cluster)
            ax.text(min_x + 0.1, max_y + 0.05, title, fontsize=8, fontweight="bold", color=_CLUSTER_TITLE)

    for layout in all_layouts:
        _draw_node(ax, layout)

    for edge in dataset.edges:
        source = layout_by_id.get(edge.source_id)
        target = layout_by_id.get(edge.target_id)
        if source and target:
            _draw_edge(ax, source, target, edge.label)

    ax.set_title(dataset.title, fontsize=12, fontweight="bold", pad=14)
    ax.axis("off")
    ax.autoscale()
    ax.margins(0.15)
    fig.tight_layout()
    save_figure(fig, output_path, profile=layout_profile_for_output(output_path))
    plt.close(fig)
