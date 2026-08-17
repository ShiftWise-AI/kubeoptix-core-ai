"""Construção de diagramas de comunicação com evidência."""

from __future__ import annotations

from kubeoptix_core_ai.models.inventory import PodLogSummary, RouteSpec, ServiceSpec
from kubeoptix_core_ai.models.workload import Workload
from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.models import DiagramEdge, DiagramNode, FlowchartDataset
from kubeoptix_core_ai.visualization.provenance import from_source, matched
from kubeoptix_core_ai.visualization.topology.matcher import workloads_for_service

_RUNTIME_SIGNAL_LABELS: dict[str, str] = {
    "oracle.jdbc": "Oracle Database (JDBC)",
}


def _provenance_from_pod_log(log: PodLogSummary, *, description: str):
    from kubeoptix_core_ai.visualization.models import EvidenceKind, ProvenanceRef

    return ProvenanceRef(
        kind=EvidenceKind.OBSERVED,
        file_path=log.file_path,
        resource_kind="PodLog",
        resource_name=log.pod_name,
        description=description,
    )


def _image_registry(image: str | None) -> str | None:
    if not image or "/" not in image:
        return None
    return image.split("/", 1)[0]


def _service_port_label(service: ServiceSpec | None, route: RouteSpec | None) -> str | None:
    if route and route.target_port is not None:
        return str(route.target_port)
    if service and service.ports:
        port = service.ports[0]
        if port.target_port is not None:
            return str(port.target_port)
        if port.port is not None:
            return str(port.port)
    return None


def _tls_edge_label(route: RouteSpec) -> str:
    termination = route.tls_termination or "none"
    if route.tls_insecure_policy == "Allow":
        return f"TLS {termination} (HTTP permitido)"
    return f"TLS {termination}"


def _external_client_node(route: RouteSpec) -> DiagramNode:
    host = route.host or route.name
    return DiagramNode(
        id=f"ext_{route.name}",
        node_type="external",
        label=f"Cliente externo<br/>{host}",
        provenance=(from_source(route.source, field_path="spec.host"),),
    )


def _router_node(route: RouteSpec) -> DiagramNode | None:
    if not route.router_name and not route.router_canonical_hostname:
        return None
    label_parts = ["OpenShift Router"]
    if route.router_name:
        label_parts.append(f"router/{route.router_name}")
    if route.router_canonical_hostname:
        label_parts.append(route.router_canonical_hostname)
    return DiagramNode(
        id=f"router_{route.name}",
        node_type="route",
        label="<br/>".join(label_parts),
        provenance=(
            from_source(route.source, field_path="status.ingress[0].routerName"),
        ),
    )


def _route_node(route: RouteSpec) -> DiagramNode:
    return DiagramNode(
        id=f"route_{route.name}",
        node_type="route",
        label=f"Route/{route.name}",
        provenance=(from_source(route.source),),
    )


def _service_node(service: ServiceSpec, *, port_hint: str | None = None) -> DiagramNode:
    port_suffix = f" :{port_hint}" if port_hint else ""
    return DiagramNode(
        id=f"svc_{service.name}",
        node_type="service",
        label=f"Service/{service.name}{port_suffix}",
        provenance=(from_source(service.source),),
    )


def _workload_node(wl: Workload) -> DiagramNode:
    return DiagramNode(
        id=f"wl_{wl.name}",
        node_type="workload",
        label=f"{wl.kind}/{wl.name}",
        provenance=(from_source(wl.source),),
    )


def _logs_for_workload(
    workload: Workload,
    logs: tuple[PodLogSummary, ...],
) -> tuple[PodLogSummary, ...]:
    return tuple(
        log
        for log in logs
        if log.app_group == workload.name or log.pod_name.startswith(f"{workload.name}-")
    )


def _runtime_signals_for_workload(
    workload: Workload,
    logs: tuple[PodLogSummary, ...],
) -> tuple[str, ...]:
    signals: set[str] = set()
    for log in _logs_for_workload(workload, logs):
        signals.update(log.runtime_signals)
    return tuple(sorted(signals))


def build_external_communication_diagrams(
    bundle: AssessmentBundle,
) -> tuple[FlowchartDataset, ...]:
    """Um diagrama por Route — tráfego externo até o workload."""
    routes = bundle.context.routes
    services = bundle.context.services
    workloads = bundle.context.workloads

    if not routes:
        return ()

    service_map = {svc.name: svc for svc in services}
    diagrams: list[FlowchartDataset] = []

    for route in sorted(routes, key=lambda r: r.name):
        if not route.target_service:
            continue

        nodes: list[DiagramNode] = []
        edges: list[DiagramEdge] = []
        seen: set[str] = set()

        def _add_node(node: DiagramNode) -> None:
            if node.id not in seen:
                nodes.append(node)
                seen.add(node.id)

        _add_node(_external_client_node(route))
        router = _router_node(route)
        if router is not None:
            _add_node(router)
            edges.append(
                DiagramEdge(
                    source_id=f"ext_{route.name}",
                    target_id=router.id,
                    edge_type="ingress",
                    label=_tls_edge_label(route),
                    evidence=(from_source(route.source, field_path="spec.tls"),),
                )
            )
            _add_node(_route_node(route))
            edges.append(
                DiagramEdge(
                    source_id=router.id,
                    target_id=f"route_{route.name}",
                    edge_type="router_admitted",
                    label="Admitted",
                    evidence=(
                        from_source(
                            route.source,
                            field_path="status.ingress[0].conditions",
                        ),
                    ),
                )
            )
        else:
            _add_node(_route_node(route))
            edges.append(
                DiagramEdge(
                    source_id=f"ext_{route.name}",
                    target_id=f"route_{route.name}",
                    edge_type="ingress",
                    label=_tls_edge_label(route),
                    evidence=(from_source(route.source, field_path="spec.host"),),
                )
            )

        svc = service_map.get(route.target_service)
        port_label = _service_port_label(svc, route)
        if svc is None:
            _add_node(
                DiagramNode(
                    id=f"svc_{route.target_service}",
                    node_type="service",
                    label=f"Service/{route.target_service}",
                    provenance=(
                        from_source(
                            route.source,
                            field_path="spec.to.name",
                            description="Service referenciado; YAML ausente",
                        ),
                    ),
                )
            )
        else:
            _add_node(_service_node(svc, port_hint=port_label))

        edges.append(
            DiagramEdge(
                source_id=f"route_{route.name}",
                target_id=f"svc_{route.target_service}",
                edge_type="routes_to",
                label=f"port {port_label}" if port_label else None,
                evidence=(from_source(route.source, field_path="spec.to.name"),),
            )
        )

        if svc is not None:
            for wl in workloads_for_service(svc, workloads):
                _add_node(_workload_node(wl))
                edges.append(
                    DiagramEdge(
                        source_id=f"svc_{svc.name}",
                        target_id=f"wl_{wl.name}",
                        edge_type="selects",
                        label="selector",
                        evidence=(
                            matched(
                                "service.spec.selector ⊆ pod template labels",
                                source=svc.source,
                            ),
                        ),
                    )
                )

        if not edges:
            continue

        diagrams.append(
            FlowchartDataset(
                title=f"Comunicação externa — {route.name}",
                question=f"Como o tráfego externo chega ao workload via Route `{route.name}`?",
                direction="LR",
                nodes=tuple(nodes),
                edges=tuple(edges),
            )
        )

    return tuple(diagrams)


def build_internal_communication_diagrams(
    bundle: AssessmentBundle,
) -> tuple[FlowchartDataset, ...]:
    """Um diagrama por Service com workloads correspondentes."""
    services = bundle.context.services
    workloads = bundle.context.workloads

    if not services:
        return ()

    diagrams: list[FlowchartDataset] = []

    for svc in sorted(services, key=lambda s: s.name):
        matched_workloads = workloads_for_service(svc, workloads)
        if not matched_workloads:
            continue

        port_label = _service_port_label(svc, None)
        nodes = [_service_node(svc, port_hint=port_label)]
        edges: list[DiagramEdge] = []

        for wl in matched_workloads:
            nodes.append(_workload_node(wl))
            edges.append(
                DiagramEdge(
                    source_id=f"svc_{svc.name}",
                    target_id=f"wl_{wl.name}",
                    edge_type="selects",
                    label="selector",
                    evidence=(
                        matched(
                            "service.spec.selector ⊆ pod template labels",
                            source=svc.source,
                        ),
                    ),
                )
            )

        diagrams.append(
            FlowchartDataset(
                title=f"Comunicação interna — {svc.name}",
                question=f"Quais pods o Service `{svc.name}` seleciona no cluster?",
                direction="LR",
                nodes=tuple(nodes),
                edges=tuple(edges),
            )
        )

    return tuple(diagrams)


def build_external_dependencies_diagrams(
    bundle: AssessmentBundle,
) -> tuple[FlowchartDataset, ...]:
    """Dependências fora do namespace/cluster com evidência nos artefatos."""
    workloads = bundle.context.workloads
    logs = bundle.context.pod_logs
    diagrams: list[FlowchartDataset] = []

    for wl in sorted(workloads, key=lambda w: w.name):
        nodes: list[DiagramNode] = [_workload_node(wl)]
        edges: list[DiagramEdge] = []
        seen: set[str] = {nodes[0].id}

        for container in wl.containers:
            if not container.image:
                continue
            registry = _image_registry(container.image)
            if registry:
                node_id = f"reg_{wl.name}_{registry.replace('.', '_').replace(':', '_')}"
                node_label = f"Registry<br/>{registry}"
            else:
                node_id = f"img_{wl.name}_{container.name}"
                node_label = f"Image<br/>{container.image[:48]}"
            if node_id not in seen:
                nodes.append(
                    DiagramNode(
                        id=node_id,
                        node_type="external",
                        label=node_label,
                        provenance=(
                            from_source(
                                wl.source,
                                field_path="spec.template.spec.containers[].image",
                                description=container.image,
                            ),
                        ),
                    )
                )
                seen.add(node_id)
            edges.append(
                DiagramEdge(
                    source_id=f"wl_{wl.name}",
                    target_id=node_id,
                    edge_type="image_pull",
                    label="image",
                    evidence=(
                        from_source(
                            wl.source,
                            field_path="spec.template.spec.containers[].image",
                        ),
                    ),
                )
            )

        pull_secret_set = set(wl.image_pull_secrets)
        for secret_name in wl.referenced_secrets:
            node_id = f"sec_{wl.name}_{secret_name}"
            if secret_name in pull_secret_set:
                edge_type = "image_pull_credential"
                edge_label = "imagePullSecrets"
                field_path = "spec.template.spec.imagePullSecrets"
            else:
                edge_type = "config_injection"
                edge_label = "envFrom"
                field_path = "envFrom.secretRef"
            if node_id not in seen:
                nodes.append(
                    DiagramNode(
                        id=node_id,
                        node_type="secret",
                        label=f"Secret/{secret_name}",
                        provenance=(from_source(wl.source, field_path=field_path),),
                    )
                )
                seen.add(node_id)
            edges.append(
                DiagramEdge(
                    source_id=f"wl_{wl.name}",
                    target_id=node_id,
                    edge_type=edge_type,
                    label=edge_label,
                    evidence=(from_source(wl.source, field_path=field_path),),
                )
            )

        workload_logs = _logs_for_workload(wl, logs)
        for signal in _runtime_signals_for_workload(wl, logs):
            label = _RUNTIME_SIGNAL_LABELS.get(signal, signal)
            node_id = f"dep_{wl.name}_{signal.replace('.', '_')}"
            evidence_logs = [log for log in workload_logs if signal in log.runtime_signals]
            if node_id not in seen:
                nodes.append(
                    DiagramNode(
                        id=node_id,
                        node_type="database",
                        label=label,
                        provenance=tuple(
                            _provenance_from_pod_log(
                                log,
                                description=f"runtime signal: {signal}",
                            )
                            for log in evidence_logs[:3]
                        ),
                    )
                )
                seen.add(node_id)
            if evidence_logs:
                edges.append(
                    DiagramEdge(
                        source_id=f"wl_{wl.name}",
                        target_id=node_id,
                        edge_type="database",
                        label="JDBC runtime",
                        evidence=(
                            _provenance_from_pod_log(
                                evidence_logs[0],
                                description="oracle.jdbc.driver em log",
                            ),
                        ),
                    )
                )

        if len(edges) == 0:
            continue

        diagrams.append(
            FlowchartDataset(
                title=f"Dependências externas — {wl.name}",
                question=f"Quais sistemas externos o workload `{wl.name}` utiliza?",
                direction="TB",
                nodes=tuple(nodes),
                edges=tuple(edges),
            )
        )

    return tuple(diagrams)


# Compatibilidade com chamadas legadas (primeiro diagrama ou agregado mínimo).
def build_external_communication_diagram(bundle: AssessmentBundle) -> FlowchartDataset | None:
    diagrams = build_external_communication_diagrams(bundle)
    return diagrams[0] if diagrams else None


def build_internal_communication_diagram(bundle: AssessmentBundle) -> FlowchartDataset | None:
    diagrams = build_internal_communication_diagrams(bundle)
    return diagrams[0] if diagrams else None
