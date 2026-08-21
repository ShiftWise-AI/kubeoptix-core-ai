"""Construção de diagramas de workloads e placement."""

from __future__ import annotations

from collections import defaultdict

from kubeoptix_core_ai.analysis.helpers import (
    derive_scheduling_pool_selector,
    matching_nodes,
    node_role_label,
)
from kubeoptix_core_ai.models.node import WorkNode
from kubeoptix_core_ai.models.workload import Workload
from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.models import DiagramEdge, DiagramNode, FlowchartDataset
from kubeoptix_core_ai.visualization.provenance import from_source, matched
from kubeoptix_core_ai.visualization.topology.matcher import services_for_workload

_MAX_NODES_PER_DIAGRAM = 15


def _workload_node(wl: Workload) -> DiagramNode:
    replicas = wl.replicas_desired
    rep_label = f" ({replicas} réplicas)" if replicas is not None else ""
    return DiagramNode(
        id=f"wl_{wl.name}",
        node_type="workload",
        label=f"{wl.kind}/{wl.name}{rep_label}",
        provenance=(from_source(wl.source),),
    )


def _resource_nodes_for_workload(wl: Workload) -> tuple[DiagramNode, ...]:
    nodes: list[DiagramNode] = []
    for vol in wl.volumes:
        if vol.volume_type == "persistentVolumeClaim" and vol.claim_name:
            nodes.append(
                DiagramNode(
                    id=f"pvc_{wl.name}_{vol.claim_name}",
                    node_type="storage",
                    label=f"PVC/{vol.claim_name}",
                    provenance=(from_source(wl.source, field_path=vol.source.field_path),),
                )
            )
    for cm_name in wl.referenced_configmaps:
        nodes.append(
            DiagramNode(
                id=f"cm_{wl.name}_{cm_name}",
                node_type="config",
                label=f"ConfigMap/{cm_name}",
                provenance=(from_source(wl.source),),
            )
        )
    for secret_name in wl.referenced_secrets:
        nodes.append(
            DiagramNode(
                id=f"sec_{wl.name}_{secret_name}",
                node_type="secret",
                label=f"Secret/{secret_name}",
                provenance=(from_source(wl.source),),
            )
        )
    if wl.hpa is not None:
        nodes.append(
            DiagramNode(
                id=f"hpa_{wl.hpa.name}",
                node_type="hpa",
                label=f"HPA/{wl.hpa.name}",
                provenance=(from_source(wl.hpa.source),),
            )
        )
    return tuple(nodes)


def build_workload_diagram(
    workloads: tuple[Workload, ...],
    services: tuple,
    *,
    partition_key: str,
    title_suffix: str = "",
) -> FlowchartDataset | None:
    if not workloads:
        return None

    nodes: list[DiagramNode] = []
    edges: list[DiagramEdge] = []

    for wl in workloads:
        wl_node = _workload_node(wl)
        nodes.append(wl_node)
        for res_node in _resource_nodes_for_workload(wl):
            nodes.append(res_node)
            edges.append(
                DiagramEdge(
                    source_id=wl_node.id,
                    target_id=res_node.id,
                    edge_type="uses",
                    evidence=(from_source(wl.source),),
                )
            )
        if wl.hpa is not None:
            edges.append(
                DiagramEdge(
                    source_id=f"hpa_{wl.hpa.name}",
                    target_id=wl_node.id,
                    edge_type="scales",
                    evidence=(from_source(wl.hpa.source),),
                )
            )
        for svc in services_for_workload(wl, services):
            svc_id = f"svc_{svc.name}"
            if not any(n.id == svc_id for n in nodes):
                nodes.append(
                    DiagramNode(
                        id=svc_id,
                        node_type="service",
                        label=f"Service/{svc.name}",
                        provenance=(from_source(svc.source),),
                    )
                )
            edges.append(
                DiagramEdge(
                    source_id=svc_id,
                    target_id=wl_node.id,
                    edge_type="selects",
                    label="selector",
                    evidence=(
                        matched(
                            f"service.spec.selector ⊆ pod template labels de {wl.name}",
                            source=svc.source,
                        ),
                    ),
                )
            )

    if len(nodes) > _MAX_NODES_PER_DIAGRAM:
        return None

    suffix = f" — {title_suffix}" if title_suffix else ""
    return FlowchartDataset(
        title=f"Diagrama de workloads{suffix}",
        question="Quais recursos Kubernetes cada workload utiliza ou expõe?",
        direction="LR",
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def iter_workload_diagram_groups(
    bundle: AssessmentBundle,
) -> tuple[tuple[FlowchartDataset, tuple[Workload, ...]], ...]:
    """Pares (diagrama, workloads) para renderização com KubeDiagrams."""
    workloads = bundle.context.workloads
    services = bundle.context.services
    if not workloads:
        return ()

    by_group: dict[str, list[Workload]] = defaultdict(list)
    for wl in workloads:
        by_group[wl.app_group].append(wl)

    groups: list[tuple[FlowchartDataset, tuple[Workload, ...]]] = []
    if len(by_group) == 1 and len(workloads) <= _MAX_NODES_PER_DIAGRAM:
        diagram = build_workload_diagram(
            workloads, services, partition_key="all", title_suffix=""
        )
        if diagram is not None:
            groups.append((diagram, workloads))
    else:
        for group, group_workloads in sorted(by_group.items()):
            wl_tuple = tuple(group_workloads)
            diagram = build_workload_diagram(
                wl_tuple, services, partition_key=group, title_suffix=group
            )
            if diagram is not None:
                groups.append((diagram, wl_tuple))
    return tuple(groups)


def build_workload_diagrams(bundle: AssessmentBundle) -> tuple[FlowchartDataset, ...]:
    return tuple(diagram for diagram, _ in iter_workload_diagram_groups(bundle))


def _node_diagram_node(node: WorkNode) -> DiagramNode:
    cpu = (
        f" CPU:{node.cpu_allocatable.raw}"
        if node.cpu_allocatable is not None
        else ""
    )
    mem = (
        f" Mem:{node.memory_allocatable.raw}"
        if node.memory_allocatable is not None
        else ""
    )
    return DiagramNode(
        id=f"node_{node.name}",
        node_type="node",
        label=f"Node/{node.name}{cpu}{mem}",
        provenance=(from_source(node.source),),
    )


def build_workload_node_diagram(bundle: AssessmentBundle) -> FlowchartDataset | None:
    workloads = bundle.context.workloads
    nodes_data = bundle.context.nodes
    if not workloads or not nodes_data:
        return None

    has_placement = any(wl.placements for wl in workloads)
    if not has_placement:
        return None

    node_map = {n.name: n for n in nodes_data}
    diagram_nodes: list[DiagramNode] = []
    edges: list[DiagramEdge] = []
    seen_nodes: set[str] = set()

    for wl in workloads:
        wl_node = _workload_node(wl)
        diagram_nodes.append(wl_node)
        for placement in wl.placements:
            node_name = placement.node_name
            if not node_name:
                continue
            node_id = f"node_{node_name}"
            if node_id not in seen_nodes:
                work_node = node_map.get(node_name)
                if work_node is not None:
                    diagram_nodes.append(_node_diagram_node(work_node))
                else:
                    role = "—"
                    diagram_nodes.append(
                        DiagramNode(
                            id=node_id,
                            node_type="node",
                            label=f"Node/{node_name}",
                            provenance=(from_source(placement.source),),
                        )
                    )
                seen_nodes.add(node_id)
            edges.append(
                DiagramEdge(
                    source_id=wl_node.id,
                    target_id=node_id,
                    edge_type="placed_on",
                    label=node_role_label(node_map[node_name]) if node_name in node_map else None,
                    evidence=(from_source(placement.source),),
                )
            )

    if not edges:
        return None

    if len(diagram_nodes) > _MAX_NODES_PER_DIAGRAM:
        selector = derive_scheduling_pool_selector(workloads)
        pool_nodes = matching_nodes(nodes_data, selector)
        pool_names = {n.name for n in pool_nodes}
        filtered_nodes: list[DiagramNode] = []
        filtered_edges: list[DiagramEdge] = []
        for edge in edges:
            if edge.target_id.replace("node_", "") in pool_names or edge.source_id.startswith("wl_"):
                filtered_edges.append(edge)
        node_ids = {e.target_id for e in filtered_edges} | {e.source_id for e in filtered_edges}
        for node in diagram_nodes:
            if node.id in node_ids:
                filtered_nodes.append(node)
        diagram_nodes = filtered_nodes
        edges = filtered_edges

    return FlowchartDataset(
        title="Placement workload × worknode",
        question="Em quais nós os pods de cada workload estão alocados?",
        direction="LR",
        nodes=tuple(diagram_nodes),
        edges=tuple(edges),
    )
