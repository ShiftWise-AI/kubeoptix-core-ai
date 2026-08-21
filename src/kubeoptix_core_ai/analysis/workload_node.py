"""Correlação workload × worknode."""

from __future__ import annotations

from collections import Counter, defaultdict

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.analysis.helpers import (
    derive_scheduling_pool_selector,
    format_cpu_millicores,
    format_memory_bytes,
    matching_nodes,
    node_matches_selector,
    pool_cpu_allocatable_millicores,
    pool_memory_allocatable_bytes,
)
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity


def analyze_workload_node(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace

    if not ctx.nodes:
        builder.add(
            category="WNODE",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            namespace=namespace,
            analysis="Nenhum worknode disponível para correlação.",
            limitation="Informação não disponível nos dados coletados.",
        )
        return

    node_by_name = {n.name: n for n in ctx.nodes}

    # Request por pod vs allocatable do nó
    for workload in ctx.workloads:
        if workload.total_cpu_request_per_pod_millicores is None:
            continue
        cpu_per_pod = workload.total_cpu_request_per_pod_millicores
        mem_per_pod = workload.total_memory_request_per_pod_bytes

        candidate_nodes = matching_nodes(ctx.nodes, workload.node_selector)
        for node in candidate_nodes:
            if node.cpu_allocatable and cpu_per_pod > node.cpu_allocatable.normalized_value:
                builder.add(
                    category="WNODE",
                    severity=Severity.CRITICAL,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="CPU request por pod excede allocatable do nó",
                            value=(
                                f"request/pod={format_cpu_millicores(cpu_per_pod)}, "
                                f"allocatable={node.cpu_allocatable.raw}"
                            ),
                            file_path=node.cpu_allocatable.source.file_path,
                        ),
                        EvidenceItem(
                            description="Nó analisado",
                            value=node.name,
                            file_path=node.source.file_path,
                        ),
                    ),
                    analysis=(
                        f"CPU request por pod ({format_cpu_millicores(cpu_per_pod)}) "
                        f"excede CPU allocatable do nó `{node.name}` "
                        f"({node.cpu_allocatable.raw})."
                    ),
                    impact="Scheduling do pod pode ser impossível neste nó.",
                    recommendation="Reduzir request ou usar nós com maior capacidade.",
                    limitation="Baseado em request configurado, não em uso real.",
                    sources=(workload.source, node.source),
                )

            if (
                mem_per_pod is not None
                and node.memory_allocatable
                and mem_per_pod > node.memory_allocatable.normalized_value
            ):
                builder.add(
                    category="WNODE",
                    severity=Severity.CRITICAL,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="Memory request por pod excede allocatable",
                            value=(
                                f"request/pod={format_memory_bytes(mem_per_pod)}, "
                                f"allocatable={node.memory_allocatable.raw}"
                            ),
                            file_path=node.memory_allocatable.source.file_path,
                        ),
                        EvidenceItem(
                            description="Nó",
                            value=node.name,
                        ),
                    ),
                    analysis=(
                        f"Memory request por pod excede allocatable do nó `{node.name}`."
                    ),
                    impact="Pod pode não ser agendado neste nó.",
                    sources=(workload.source, node.source),
                )

    # Concentração de placements
    for workload in ctx.workloads:
        if not workload.placements:
            continue

        by_node: Counter[str] = Counter()
        for p in workload.placements:
            if p.node_name:
                by_node[p.node_name] += 1

        if workload.replicas_desired and workload.replicas_desired >= 2:
            for node_name, count in by_node.items():
                if count >= 2:
                    builder.add(
                        category="WNODE",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.HIGH,
                        namespace=namespace,
                        workload=workload.name,
                        evidence=(
                            EvidenceItem(
                                description="Concentração de pods no mesmo nó",
                                value=f"nó={node_name}, pods={count}",
                            ),
                            EvidenceItem(
                                description="Placements observados",
                                value=str(dict(by_node)),
                            ),
                        ),
                        analysis=(
                            f"`{workload.name}` possui {count} pod(s) no nó `{node_name}`."
                        ),
                        impact="Reduz resiliência a falha de nó único.",
                        recommendation="Configurar podAntiAffinity ou topologySpread.",
                        sources=(workload.source,),
                    )

        # Pod em nó fora do nodeSelector
        for placement in workload.placements:
            if not placement.node_name or not workload.node_selector:
                continue
            node = node_by_name.get(placement.node_name)
            if node and not node_matches_selector(node, workload.node_selector):
                builder.add(
                    category="WNODE",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="Pod em nó fora do nodeSelector",
                            value=(
                                f"pod={placement.pod_name}, nó={placement.node_name}, "
                                f"selector={workload.node_selector}"
                            ),
                            file_path=placement.source.file_path,
                        ),
                    ),
                    analysis=(
                        f"Pod `{placement.pod_name}` está em `{placement.node_name}`, "
                        "que não satisfaz o nodeSelector do workload."
                    ),
                    impact="Pode indicar agendamento em pool inadequado.",
                    sources=(placement.source, workload.source),
                )

    # Concentração cross-workload no mesmo nó (namespace inteiro)
    node_workloads: dict[str, list[str]] = defaultdict(list)
    for workload in ctx.workloads:
        for placement in workload.placements:
            if placement.node_name:
                node_workloads[placement.node_name].append(workload.name)

    for node_name, wl_names in node_workloads.items():
        unique = set(wl_names)
        if len(unique) >= 2 and len(wl_names) >= 3:
            builder.add(
                category="WNODE",
                severity=Severity.INFO,
                confidence=Confidence.MEDIUM,
                namespace=namespace,
                evidence=(
                    EvidenceItem(
                        description="Múltiplos workloads no mesmo nó",
                        value=f"nó={node_name}, workloads={sorted(unique)}",
                    ),
                ),
                analysis=(
                    f"O nó `{node_name}` hospeda pods de {len(unique)} workloads: "
                    f"{', '.join(sorted(unique))}."
                ),
                impact="Concentração de carga de múltiplas aplicações no mesmo nó.",
                sources=(),
            )

    # Resumo pool vs namespace (pool derivado do nodeSelector majoritário)
    selector = derive_scheduling_pool_selector(ctx.workloads)
    pool_nodes = matching_nodes(ctx.nodes, selector)
    pool_cpu = pool_cpu_allocatable_millicores(pool_nodes)
    pool_mem = pool_memory_allocatable_bytes(pool_nodes)

    if pool_cpu and pool_mem:
        ns_cpu = sum(
            (w.total_cpu_request_per_pod_millicores or 0) * (w.replicas_desired or 0)
            for w in ctx.workloads
        )
        ns_mem = sum(
            (w.total_memory_request_per_pod_bytes or 0) * (w.replicas_desired or 0)
            for w in ctx.workloads
        )
        selector_desc = (
            ", ".join(f"{k}={v}" for k, v in sorted(selector.items()))
            if selector
            else "todos os nós coletados"
        )
        builder.add(
            category="WNODE",
            severity=Severity.INFO,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="CPU request namespace vs pool allocatable",
                    value=(
                        f"namespace={format_cpu_millicores(ns_cpu)}, "
                        f"pool={format_cpu_millicores(pool_cpu)}"
                    ),
                ),
                EvidenceItem(
                    description="Memory request namespace vs pool allocatable",
                    value=(
                        f"namespace={format_memory_bytes(ns_mem)}, "
                        f"pool={format_memory_bytes(pool_mem)}"
                    ),
                ),
                EvidenceItem(
                    description="Pool de scheduling",
                    value=f"selector={selector_desc}, nós={len(pool_nodes)}",
                ),
            ),
            analysis=(
                f"Requests do namespace representam "
                f"{ns_cpu / pool_cpu * 100:.2f}% CPU e "
                f"{ns_mem / pool_mem * 100:.2f}% memória do pool allocatable "
                f"({len(pool_nodes)} nós, pool `{selector_desc}`)."
            ),
            limitation=(
                "Capacidade reservada (requests), não consumo real. "
                "Pool compartilhado entre namespaces."
            ),
        )

    _analyze_datacenter_placement(ctx, builder)
    _analyze_app_pool_capacity(ctx, builder)


def _analyze_datacenter_placement(
    ctx: AnalysisContext,
    builder: FindingBuilder,
) -> None:
    node_by_name = {n.name: n for n in ctx.nodes}
    namespace = ctx.namespace

    dc_counts: Counter[str] = Counter()
    unknown = 0
    for workload in ctx.workloads:
        for placement in workload.placements:
            if not placement.node_name:
                continue
            node = node_by_name.get(placement.node_name)
            if node and node.datacenter:
                dc_counts[node.datacenter] += 1
            else:
                unknown += 1

    if dc_counts:
        builder.add(
            category="WNODE",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="Pods por datacenter",
                    value=str(dict(dc_counts)),
                ),
                EvidenceItem(
                    description="Pods sem datacenter no nó",
                    value=str(unknown),
                ),
            ),
            analysis=(
                "Distribuição de pods do namespace entre datacenters: "
                + ", ".join(f"{dc}={count}" for dc, count in sorted(dc_counts.items()))
                + ("." if not unknown else f" ({unknown} sem label datacenter).")
            ),
            limitation="Baseado em label `datacenter` dos worknodes e placement dos pods.",
        )

    for workload in ctx.workloads:
        if not workload.placements:
            continue
        desired = workload.replicas_desired or len(workload.placements)
        if desired < 2:
            continue
        dcs: set[str] = set()
        for placement in workload.placements:
            node = node_by_name.get(placement.node_name or "")
            if node and node.datacenter:
                dcs.add(node.datacenter)
        if len(dcs) == 1 and len(workload.placements) >= 2:
            only_dc = next(iter(dcs))
            builder.add(
                category="WNODE",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="Datacenters com pods do workload",
                        value=only_dc,
                    ),
                    EvidenceItem(
                        description="Pods observados",
                        value=str(len(workload.placements)),
                    ),
                ),
                analysis=(
                    f"`{workload.name}` possui {len(workload.placements)} pod(s) "
                    f"somente no datacenter `{only_dc}`."
                ),
                impact="Falha do datacenter único indisponibiliza todas as réplicas observadas.",
                recommendation=(
                    "Distribuir réplicas entre datacenters (labels `datacenter`) "
                    "via topologySpreadConstraints ou afinidade."
                ),
                sources=(workload.source,),
            )


def _analyze_app_pool_capacity(
    ctx: AnalysisContext,
    builder: FindingBuilder,
) -> None:
    app_nodes = tuple(n for n in ctx.nodes if n.role == "app")
    if len(app_nodes) < 2:
        return

    mem_values = [
        n.memory_allocatable.normalized_value
        for n in app_nodes
        if n.memory_allocatable is not None
    ]
    cpu_values = [
        n.cpu_allocatable.normalized_value
        for n in app_nodes
        if n.cpu_allocatable is not None
    ]
    if len(mem_values) < 2:
        return

    mem_min, mem_max = min(mem_values), max(mem_values)
    if mem_max <= 0 or mem_min / mem_max >= 0.85:
        return

    dcs = sorted({n.datacenter or "—" for n in app_nodes})
    cpu_display = "—"
    if cpu_values:
        cpu_display = (
            f"{format_cpu_millicores(min(cpu_values))}–"
            f"{format_cpu_millicores(max(cpu_values))}"
        )
    builder.add(
        category="WNODE",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        namespace=ctx.namespace,
        evidence=(
            EvidenceItem(
                description="Pool type=app",
                value=(
                    f"nós={len(app_nodes)}, datacenters={dcs}, "
                    f"mem={format_memory_bytes(mem_min)}–{format_memory_bytes(mem_max)}, "
                    f"cpu={cpu_display}"
                ),
            ),
        ),
        analysis=(
            f"O pool `type=app` tem {len(app_nodes)} nós em {', '.join(dcs)} "
            f"com memória allocatable heterogênea "
            f"({format_memory_bytes(mem_min)} a {format_memory_bytes(mem_max)})."
        ),
        impact=(
            "Pods com memory request acima do menor nó do pool só agendam "
            "em um subconjunto dos workers."
        ),
        recommendation=(
            "Dimensionar requests pelo menor nó do pool app ou separar pools "
            "por capacidade."
        ),
    )
