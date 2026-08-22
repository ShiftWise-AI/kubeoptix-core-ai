"""Diagrama consolidado de arquitetura do namespace (artefatos estáticos YAML)."""

from __future__ import annotations

import re

from kubeoptix_core_ai.analysis.namespace_partition import ProposedNamespace
from kubeoptix_core_ai.analysis.workload_refs import (
    extract_cross_namespace_service_refs,
    extract_database_refs,
    extract_service_calls,
)
from kubeoptix_core_ai.models.inventory import RouteSpec, ServiceSpec
from kubeoptix_core_ai.models.workload import Workload
from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.datasets.communication import _tls_edge_label
from kubeoptix_core_ai.visualization.models import (
    DiagramEdge,
    DiagramNode,
    FlowchartDataset,
    FlowchartSubgraph,
)
from kubeoptix_core_ai.visualization.provenance import from_source, matched
from kubeoptix_core_ai.visualization.topology.matcher import workloads_for_service

_SUBGRAPH_CURRENT = "ns_current"
_SUBGRAPH_OTHER = "ns_other"
_SUBGRAPH_EXTERNAL = "external"

_SCOPE_LABELS = {
    "internal": "interno",
    "cross_namespace": "entre namespaces",
    "external": "externo",
}


def _edge_label(scope: str | None, detail: str | None) -> str | None:
    if scope and detail:
        return f"{detail} · {_SCOPE_LABELS[scope]}"
    if scope:
        return _SCOPE_LABELS[scope]
    return detail


def _pod_instance_label(workload: Workload) -> str:
    """Rótulo do Pod com contagem de instâncias evidenciada no inventário YAML."""
    desired = workload.replicas_desired
    ready = workload.replicas_ready
    placements = len(workload.placements)

    if desired is not None and ready is not None:
        count = f"{desired}/{ready} inst."
    elif desired is not None:
        count = f"{desired} inst."
    elif placements > 0:
        count = f"{placements} inst."
    else:
        return f"Pod/{workload.name}"

    return f"Pod/{workload.name} ({count})"


def _pod_node(wl: Workload) -> DiagramNode:
    return DiagramNode(
        id=f"pod_{wl.name}",
        node_type="workload",
        label=_pod_instance_label(wl),
        subgraph=_SUBGRAPH_CURRENT,
        provenance=(from_source(wl.source),),
    )


def _service_node(service: ServiceSpec) -> DiagramNode:
    return DiagramNode(
        id=f"svc_{service.name}",
        node_type="service",
        label=f"Service/{service.name}",
        subgraph=_SUBGRAPH_CURRENT,
        provenance=(from_source(service.source),),
    )


def _route_node(route: RouteSpec) -> DiagramNode:
    return DiagramNode(
        id=f"route_{route.name}",
        node_type="route",
        label=f"Route/{route.name}",
        subgraph=_SUBGRAPH_CURRENT,
        provenance=(from_source(route.source),),
    )


def _external_node(node_id: str, label: str, *, provenance: tuple) -> DiagramNode:
    return DiagramNode(
        id=node_id,
        node_type="external",
        label=label,
        subgraph=_SUBGRAPH_EXTERNAL,
        provenance=provenance,
    )


def _database_node(node_id: str, label: str, *, provenance: tuple) -> DiagramNode:
    return DiagramNode(
        id=node_id,
        node_type="database",
        label=label,
        subgraph=_SUBGRAPH_EXTERNAL,
        provenance=provenance,
    )


def _other_namespace_node(node_id: str, label: str, *, provenance: tuple) -> DiagramNode:
    return DiagramNode(
        id=node_id,
        node_type="messaging",
        label=label,
        subgraph=_SUBGRAPH_OTHER,
        provenance=provenance,
    )


def _add_edge(
    edges: list[DiagramEdge],
    *,
    source_id: str,
    target_id: str,
    edge_type: str,
    label: str | None = None,
    scope: str | None = None,
    evidence: tuple = (),
) -> None:
    edges.append(
        DiagramEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            label=_edge_label(scope, label),
            communication_scope=scope,  # type: ignore[arg-type]
            evidence=evidence,
        )
    )


def build_namespace_architecture_diagram(
    bundle: AssessmentBundle,
    *,
    workloads: tuple[Workload, ...] | None = None,
    title: str | None = None,
    current_subgraph_title: str | None = None,
    question: str | None = None,
) -> FlowchartDataset | None:
    """
    Diagrama simplificado de comunicação: Pods, Services, Routes, bancos e externos.

    Não inclui Secrets, imagens de container nem ConfigMaps. Apenas relações
    comprováveis nos YAMLs estáticos do inventário.
    """
    namespace = bundle.analysis.namespace
    all_workloads = bundle.context.workloads
    focus = workloads if workloads is not None else all_workloads
    focus_names = {wl.name for wl in focus}
    services = bundle.context.services
    routes = bundle.context.routes
    is_subset = workloads is not None and focus_names != {wl.name for wl in all_workloads}

    nodes: dict[str, DiagramNode] = {}
    edges: list[DiagramEdge] = []

    def _ensure_node(node: DiagramNode) -> None:
        nodes.setdefault(node.id, node)

    service_map = {svc.name: svc for svc in services}
    service_names = set(service_map)
    in_group_services = {
        svc.name
        for svc in services
        if any(wl.name in focus_names for wl in workloads_for_service(svc, all_workloads))
    }
    database_nodes: dict[str, str] = {}

    def _ensure_pod(wl: Workload) -> str:
        pod_id = f"pod_{wl.name}"
        _ensure_node(_pod_node(wl))
        return pod_id

    def _ensure_service(svc: ServiceSpec, *, subgraph: str | None = None) -> str:
        svc_id = f"svc_{svc.name}"
        node = _service_node(svc)
        if subgraph is not None:
            node = node.model_copy(update={"subgraph": subgraph})
        _ensure_node(node)
        return svc_id

    # Service → Pod (selector)
    for svc in services:
        selected = [
            wl for wl in workloads_for_service(svc, all_workloads) if wl.name in focus_names
        ]
        if not selected:
            continue
        for wl in selected:
            _add_edge(
                edges,
                source_id=_ensure_service(svc),
                target_id=_ensure_pod(wl),
                edge_type="selects",
                scope="internal",
                label="selector",
                evidence=(
                    matched(
                        "service.spec.selector ⊆ pod template labels",
                        source=svc.source,
                    ),
                ),
            )

    # Externo → Route → Service
    for route in routes:
        if not route.target_service:
            continue
        if is_subset and route.target_service not in in_group_services:
            continue

        host = route.host or route.name
        ext_id = f"ext_client_{route.name}"
        _ensure_node(
            _external_node(
                ext_id,
                f"Cliente externo / {host}",
                provenance=(from_source(route.source, field_path="spec.host"),),
            )
        )
        route_id = f"route_{route.name}"
        _ensure_node(_route_node(route))

        _add_edge(
            edges,
            source_id=ext_id,
            target_id=route_id,
            edge_type="ingress",
            scope="external",
            label=_tls_edge_label(route),
            evidence=(from_source(route.source, field_path="spec.host"),),
        )

        target_svc = service_map.get(route.target_service)
        if target_svc is None:
            _ensure_node(
                DiagramNode(
                    id=f"svc_{route.target_service}",
                    node_type="service",
                    label=f"Service/{route.target_service}",
                    subgraph=_SUBGRAPH_CURRENT,
                    provenance=(
                        from_source(
                            route.source,
                            field_path="spec.to.name",
                            description="Service referenciado; YAML ausente no inventário",
                        ),
                    ),
                )
            )
        svc_id = f"svc_{route.target_service}"
        _add_edge(
            edges,
            source_id=route_id,
            target_id=svc_id,
            edge_type="routes_to",
            scope="internal",
            label="spec.to",
            evidence=(from_source(route.source, field_path="spec.to.name"),),
        )

    # Service ExternalName → destino externo
    for svc in services:
        if not svc.external_name:
            continue
        if is_subset and svc.name not in in_group_services:
            continue
        ext_id = f"ext_name_{svc.name}"
        _ensure_node(
            _external_node(
                ext_id,
                f"Destino externo / {svc.external_name}",
                provenance=(from_source(svc.source, field_path="spec.externalName"),),
            )
        )
        _add_edge(
            edges,
            source_id=_ensure_service(svc),
            target_id=ext_id,
            edge_type="external_name",
            scope="external",
            label="ExternalName",
            evidence=(from_source(svc.source, field_path="spec.externalName"),),
        )

    for wl in focus:
        # Pod → Service interno (variáveis de ambiente)
        for service_name, field_path, env_name in extract_service_calls(wl, service_names):
            svc = service_map[service_name]
            detail = f"env {env_name}" if env_name else "env"
            outside = is_subset and service_name not in in_group_services
            subgraph = _SUBGRAPH_OTHER if outside else None
            scope = "cross_namespace" if outside else "internal"
            _add_edge(
                edges,
                source_id=_ensure_pod(wl),
                target_id=_ensure_service(svc, subgraph=subgraph),
                edge_type="http_call",
                scope=scope,
                label=detail,
                evidence=(from_source(wl.source, field_path=field_path),),
            )

        # Pod → Banco de dados (credencial nomeada no YAML)
        for db_hint, field_path in extract_database_refs(wl):
            db_id = database_nodes.get(db_hint)
            if db_id is None:
                safe = re.sub(r"[^a-zA-Z0-9_]", "_", db_hint)[:40]
                db_id = f"db_{safe}"
                database_nodes[db_hint] = db_id
                label = (
                    f"Banco de dados / {db_hint}"
                    if len(db_hint) <= 48
                    else "Banco de dados"
                )
                _ensure_node(
                    _database_node(
                        db_id,
                        label,
                        provenance=(from_source(wl.source, field_path=field_path),),
                    )
                )
            _add_edge(
                edges,
                source_id=_ensure_pod(wl),
                target_id=db_id,
                edge_type="database",
                scope="external",
                label="credenciais DB",
                evidence=(from_source(wl.source, field_path=field_path),),
            )

        # Pod → recurso em outro namespace (somente DB evidenciado)
        for other_ns, name, field_path in extract_cross_namespace_service_refs(wl):
            other_id = f"other_db_{other_ns}_{name}".replace("-", "_")
            _ensure_node(
                _other_namespace_node(
                    other_id,
                    f"Banco de dados / {name} ({other_ns})",
                    provenance=(
                        from_source(
                            wl.source,
                            field_path=field_path,
                            description=f"namespace={other_ns}",
                        ),
                    ),
                )
            )
            _add_edge(
                edges,
                source_id=_ensure_pod(wl),
                target_id=other_id,
                edge_type="cross_namespace_db",
                scope="cross_namespace",
                label=f"namespace={other_ns}",
                evidence=(from_source(wl.source, field_path=field_path),),
            )

    if not edges:
        return None

    # Mantém apenas nós participantes de alguma aresta
    connected_ids = {e.source_id for e in edges} | {e.target_id for e in edges}
    nodes = {node_id: node for node_id, node in nodes.items() if node_id in connected_ids}

    current_title = current_subgraph_title or f"Namespace atual ({namespace})"
    subgraphs = (
        FlowchartSubgraph(id=_SUBGRAPH_CURRENT, title=current_title),
        FlowchartSubgraph(id=_SUBGRAPH_OTHER, title="Outros namespaces"),
        FlowchartSubgraph(id=_SUBGRAPH_EXTERNAL, title="Fora do cluster"),
    )

    return FlowchartDataset(
        title=title or "Arquitetura do namespace",
        question=question
        or "Como Pods, Services, Routes e dependências externas se comunicam?",
        direction="LR",
        nodes=tuple(nodes.values()),
        edges=tuple(edges),
        subgraphs=subgraphs,
    )


def build_proposed_namespace_architecture_diagram(
    bundle: AssessmentBundle,
    proposal: ProposedNamespace,
) -> FlowchartDataset | None:
    """Arquitetura do recorte de workloads proposto como namespace distinto."""
    selected = tuple(
        wl for wl in bundle.context.workloads if wl.name in set(proposal.workload_names)
    )
    if not selected:
        return None
    return build_namespace_architecture_diagram(
        bundle,
        workloads=selected,
        title=f"Arquitetura proposta — `{proposal.suggested_name}`",
        current_subgraph_title=f"Namespace proposto ({proposal.suggested_name})",
        question=(
            "Como ficaria a arquitetura deste recorte após a quebra do namespace?"
        ),
    )
