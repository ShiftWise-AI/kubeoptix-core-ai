"""Diagrama consolidado de arquitetura do namespace (artefatos estáticos YAML)."""

from __future__ import annotations

import re

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

_DATABASE_SECRET_MARKERS = (
    "database",
    "db-",
    "-db",
    "jdbc",
    "postgres",
    "oracle",
    "mysql",
    "mongo",
    "mariadb",
    "sql",
)

_SERVICE_REF_PATTERNS = (
    re.compile(r"https?://([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)(?::|/|$)", re.I),
    re.compile(r"\b([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\.[a-z0-9][a-z0-9.-]*\.svc(?:\.cluster\.local)?\b", re.I),
    re.compile(r"\b([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\.svc(?:\.cluster\.local)?\b", re.I),
)


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


def _load_deployment_document(workload: Workload) -> dict | None:
    from pathlib import Path

    from kubeoptix_core_ai.parsers.base import load_yaml_file

    try:
        return load_yaml_file(Path(workload.source.file_path))
    except OSError:
        return None


def _container_specs(workload: Workload) -> list[dict]:
    document = _load_deployment_document(workload)
    if not document:
        return []
    template_spec = (
        (document.get("spec") or {}).get("template") or {}
    ).get("spec") or {}
    containers = template_spec.get("containers") or []
    return [c for c in containers if isinstance(c, dict)]


def _is_database_secret_name(name: str) -> bool:
    lower = name.lower()
    return any(marker in lower for marker in _DATABASE_SECRET_MARKERS)


def _extract_database_refs(
    workload: Workload,
) -> tuple[tuple[str, str], ...]:
    """Referências a banco de dados via nome de Secret no YAML (sem ler conteúdo)."""
    refs: list[tuple[str, str]] = []
    for c_idx, container in enumerate(_container_specs(workload)):
        for ef_idx, env_from in enumerate(container.get("envFrom") or []):
            if not isinstance(env_from, dict):
                continue
            secret_ref = env_from.get("secretRef")
            if not isinstance(secret_ref, dict):
                continue
            name = secret_ref.get("name")
            if not name or not _is_database_secret_name(str(name)):
                continue
            field_path = f"spec.template.spec.containers[{c_idx}].envFrom[{ef_idx}].secretRef"
            refs.append((str(name), field_path))
        for e_idx, env in enumerate(container.get("env") or []):
            if not isinstance(env, dict):
                continue
            value = env.get("value")
            if not isinstance(value, str):
                continue
            if "jdbc:" in value.lower() or "database" in value.lower():
                refs.append((value[:48], f"spec.template.spec.containers[{c_idx}].env[{e_idx}].value"))
    return tuple(refs)


def _extract_service_calls(
    workload: Workload,
    service_names: set[str],
) -> tuple[tuple[str, str, str], ...]:
    """Chamadas a Services internos evidenciadas em variáveis de ambiente."""
    calls: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    for c_idx, container in enumerate(_container_specs(workload)):
        for e_idx, env in enumerate(container.get("env") or []):
            if not isinstance(env, dict):
                continue
            value = env.get("value")
            if not isinstance(value, str):
                continue
            env_name = str(env.get("name", ""))
            field_path = f"spec.template.spec.containers[{c_idx}].env[{e_idx}].value"
            for pattern in _SERVICE_REF_PATTERNS:
                for match in pattern.finditer(value):
                    service_name = match.group(1).lower()
                    if service_name not in service_names:
                        continue
                    if service_name == workload.name.lower():
                        continue
                    key = (service_name, field_path)
                    if key in seen:
                        continue
                    seen.add(key)
                    calls.append((service_name, field_path, env_name))
    return tuple(calls)


def _extract_cross_namespace_service_refs(
    workload: Workload,
) -> tuple[tuple[str, str, str], ...]:
    """Services em outros namespaces referenciados explicitamente no YAML."""
    refs: list[tuple[str, str, str]] = []
    for c_idx, container in enumerate(_container_specs(workload)):
        for e_idx, env in enumerate(container.get("env") or []):
            if not isinstance(env, dict):
                continue
            value_from = env.get("valueFrom")
            if not isinstance(value_from, dict):
                continue
            for ref_key in ("configMapKeyRef", "secretKeyRef"):
                if ref_key not in value_from or not isinstance(value_from[ref_key], dict):
                    continue
                ref = value_from[ref_key]
                other_ns = ref.get("namespace")
                name = ref.get("name")
                if not other_ns or not name or other_ns == workload.namespace:
                    continue
                if not _is_database_secret_name(str(name)):
                    continue
                field_path = f"spec.template.spec.containers[{c_idx}].env[{e_idx}].valueFrom.{ref_key}"
                refs.append((str(other_ns), str(name), field_path))
    return tuple(refs)


def build_namespace_architecture_diagram(
    bundle: AssessmentBundle,
) -> FlowchartDataset | None:
    """
    Diagrama simplificado de comunicação: Pods, Services, Routes, bancos e externos.

    Não inclui Secrets, imagens de container nem ConfigMaps. Apenas relações
    comprováveis nos YAMLs estáticos do inventário.
    """
    namespace = bundle.analysis.namespace
    workloads = bundle.context.workloads
    services = bundle.context.services
    routes = bundle.context.routes

    nodes: dict[str, DiagramNode] = {}
    edges: list[DiagramEdge] = []

    def _ensure_node(node: DiagramNode) -> None:
        nodes.setdefault(node.id, node)

    service_map = {svc.name: svc for svc in services}
    service_names = set(service_map)
    database_nodes: dict[str, str] = {}

    def _ensure_pod(wl: Workload) -> str:
        pod_id = f"pod_{wl.name}"
        _ensure_node(_pod_node(wl))
        return pod_id

    def _ensure_service(svc: ServiceSpec) -> str:
        svc_id = f"svc_{svc.name}"
        _ensure_node(_service_node(svc))
        return svc_id

    # Service → Pod (selector)
    for svc in services:
        for wl in workloads_for_service(svc, workloads):
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

    for wl in workloads:
        # Pod → Service interno (variáveis de ambiente)
        for service_name, field_path, env_name in _extract_service_calls(wl, service_names):
            svc = service_map[service_name]
            detail = f"env {env_name}" if env_name else "env"
            _add_edge(
                edges,
                source_id=_ensure_pod(wl),
                target_id=_ensure_service(svc),
                edge_type="http_call",
                scope="internal",
                label=detail,
                evidence=(from_source(wl.source, field_path=field_path),),
            )

        # Pod → Banco de dados (credencial nomeada no YAML)
        for db_hint, field_path in _extract_database_refs(wl):
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
        for other_ns, name, field_path in _extract_cross_namespace_service_refs(wl):
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

    subgraphs = (
        FlowchartSubgraph(id=_SUBGRAPH_CURRENT, title=f"Namespace atual ({namespace})"),
        FlowchartSubgraph(id=_SUBGRAPH_OTHER, title="Outros namespaces"),
        FlowchartSubgraph(id=_SUBGRAPH_EXTERNAL, title="Fora do cluster"),
    )

    return FlowchartDataset(
        title="Arquitetura do namespace",
        question="Como Pods, Services, Routes e dependências externas se comunicam?",
        direction="LR",
        nodes=tuple(nodes.values()),
        edges=tuple(edges),
        subgraphs=subgraphs,
    )
