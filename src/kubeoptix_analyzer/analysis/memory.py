"""Análise determinística de memória."""

from __future__ import annotations

from kubeoptix_analyzer.analysis.context import AnalysisContext
from kubeoptix_analyzer.analysis.findings_builder import FindingBuilder
from kubeoptix_analyzer.analysis.helpers import (
    format_memory_bytes,
    matching_nodes,
    pool_memory_allocatable_bytes,
    workload_total_memory_request_bytes,
)
from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Severity

_MEMORY_USAGE_ABOVE_REQUEST_RATIO = 1.0
_NAMESPACE_MEM_POOL_MEDIUM_RATIO = 0.25
_NAMESPACE_MEM_POOL_HIGH_RATIO = 0.50


def analyze_memory(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace

    for workload in ctx.workloads:
        for container in workload.containers:
            if container.memory_request is None:
                builder.add(
                    category="MEM",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="Memória request não configurada",
                            field_path="spec.template.spec.containers[].resources.requests.memory",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis=(
                        f"O container `{container.name}` do workload `{workload.name}` "
                        "não define memory request."
                    ),
                    impact="Pod pode ser classificado como BestEffort para memória.",
                    recommendation="Definir memory request conforme footprint esperado.",
                    sources=(workload.source,),
                )

            if container.memory_limit is None:
                builder.add(
                    category="MEM",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="Memória limit não configurada",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis=f"O container `{container.name}` não define memory limit.",
                    impact="Sem limit, o container pode consumir memória do nó sem teto.",
                    recommendation="Definir memory limit para evitar pressão no nó.",
                    sources=(workload.source,),
                )

    if ctx.has_runtime_metrics:
        for workload in ctx.workloads:
            for snapshot in workload.metrics:
                for cm in snapshot.containers:
                    container_spec = next(
                        (c for c in workload.containers if c.name == cm.container_name),
                        None,
                    )
                    if not container_spec or not container_spec.memory_request:
                        continue
                    if not cm.memory_usage:
                        continue
                    usage = cm.memory_usage.normalized_value
                    request = container_spec.memory_request.normalized_value
                    if request <= 0:
                        continue
                    ratio = usage / request
                    if ratio > _MEMORY_USAGE_ABOVE_REQUEST_RATIO:
                        builder.add(
                            category="MEM",
                            severity=Severity.HIGH,
                            confidence=Confidence.HIGH,
                            namespace=namespace,
                            workload=workload.name,
                            container=cm.container_name,
                            evidence=(
                                EvidenceItem(
                                    description="Memória usage (snapshot) acima do request",
                                    field_path=cm.memory_usage.source.field_path,
                                    value=(
                                        f"usage={cm.memory_usage.raw}, "
                                        f"request={container_spec.memory_request.raw}"
                                    ),
                                    file_path=cm.memory_usage.source.file_path,
                                    container=cm.container_name,
                                ),
                                EvidenceItem(
                                    description="Pod analisado",
                                    value=snapshot.pod_name,
                                    file_path=snapshot.source.file_path,
                                ),
                            ),
                            analysis=(
                                f"No snapshot coletado, o uso de memória "
                                f"({cm.memory_usage.raw}) excede o request configurado "
                                f"({container_spec.memory_request.raw}) — "
                                f"aproximadamente {ratio * 100:.1f}% do request."
                            ),
                            impact=(
                                "Em pressão de memória no nó, pods com uso acima do request "
                                "têm maior prioridade de eviction (classe Burstable)."
                            ),
                            recommendation=(
                                "Avaliar aumento do memory request para refletir o consumo "
                                "observado neste snapshot."
                            ),
                            limitation=(
                                "Snapshot pontual (PodMetrics); não comprova OOMKilled nem "
                                "série histórica de picos."
                            ),
                            sources=(snapshot.source, workload.source),
                        )
    else:
        builder.add(
            category="MEM",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            namespace=namespace,
            analysis=(
                "A análise de utilização real de memória não foi realizada devido à "
                "ausência de métricas de runtime nos dados disponíveis."
            ),
            limitation="Informação não disponível nos dados coletados.",
        )

    selectors = {tuple(sorted(w.node_selector.items())) for w in ctx.workloads if w.node_selector}
    if not selectors:
        selectors = {()}

    for selector_tuple in selectors:
        selector = dict(selector_tuple)
        pool_nodes = matching_nodes(ctx.nodes, selector)
        pool_mem = pool_memory_allocatable_bytes(pool_nodes)
        if pool_mem is None:
            continue

        ns_mem = 0.0
        has_ns_mem = False
        for workload in ctx.workloads:
            if selector and workload.node_selector != selector:
                continue
            total = workload_total_memory_request_bytes(workload)
            if total is not None:
                ns_mem += total
                has_ns_mem = True

        if not has_ns_mem or pool_mem <= 0:
            continue

        ratio = ns_mem / pool_mem
        if ratio >= _NAMESPACE_MEM_POOL_HIGH_RATIO:
            sev = Severity.HIGH
        elif ratio >= _NAMESPACE_MEM_POOL_MEDIUM_RATIO:
            sev = Severity.MEDIUM
        else:
            continue

        builder.add(
            category="MEM",
            severity=sev,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="Memory request total do namespace (derivado)",
                    value=format_memory_bytes(ns_mem),
                ),
                EvidenceItem(
                    description="Memória allocatable do pool (derivado)",
                    value=format_memory_bytes(pool_mem),
                ),
            ),
            analysis=(
                f"Os requests de memória do namespace somam {format_memory_bytes(ns_mem)} "
                f"({ratio * 100:.1f}% do allocatable do pool)."
            ),
            impact="Reserva significativa de memória no pool de nós compatível.",
            recommendation="Validar sizing e crescimento de réplicas no pool.",
            limitation="Baseado em requests, não em uso real. Pool compartilhado.",
        )
