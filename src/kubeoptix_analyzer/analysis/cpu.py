"""Análise determinística de CPU."""

from __future__ import annotations

from kubeoptix_analyzer.analysis.context import AnalysisContext
from kubeoptix_analyzer.analysis.findings_builder import FindingBuilder
from kubeoptix_analyzer.analysis.helpers import (
    format_cpu_millicores,
    matching_nodes,
    pool_cpu_allocatable_millicores,
    workload_total_cpu_request_millicores,
)
from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Severity

# Uso de CPU (métrica) abaixo de 10% do request configurado → sinal de superdimensionamento
_CPU_USAGE_LOW_RATIO = 0.10
# Request de namespace > 25% / 50% do pool allocatable compatível
_NAMESPACE_CPU_POOL_MEDIUM_RATIO = 0.25
_NAMESPACE_CPU_POOL_HIGH_RATIO = 0.50


def analyze_cpu(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace

    # --- Por container: ausência de request/limit ---
    for workload in ctx.workloads:
        for container in workload.containers:
            if container.cpu_request is None:
                builder.add(
                    category="CPU",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="CPU request não configurado",
                            field_path="spec.template.spec.containers[].resources.requests.cpu",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis=(
                        f"O container `{container.name}` do workload `{workload.name}` "
                        "não define CPU request."
                    ),
                    impact=(
                        "Sem request, o scheduler não reserva CPU para o pod e a "
                        "classificação de QoS pode ser afetada."
                    ),
                    recommendation="Definir CPU request alinhado ao perfil esperado da aplicação.",
                    sources=(workload.source,),
                )

            if container.cpu_limit is None:
                builder.add(
                    category="CPU",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="CPU limit não configurado",
                            field_path="spec.template.spec.containers[].resources.limits.cpu",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis=(
                        f"O container `{container.name}` não define CPU limit."
                    ),
                    impact="Ausência de limit pode permitir consumo ilimitado de CPU no nó.",
                    recommendation="Definir CPU limit para conter picos de consumo.",
                    sources=(workload.source,),
                )

            if (
                container.cpu_request is not None
                and container.cpu_limit is not None
                and container.cpu_request.normalized_value
                > container.cpu_limit.normalized_value
            ):
                builder.add(
                    category="CPU",
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="CPU request maior que limit",
                            field_path=container.cpu_request.source.field_path,
                            value=f"request={container.cpu_request.raw}, limit={container.cpu_limit.raw}",
                            file_path=container.cpu_request.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis=(
                        f"CPU request ({container.cpu_request.raw}) excede "
                        f"CPU limit ({container.cpu_limit.raw})."
                    ),
                    impact="Configuração inválida ou inconsistente para o scheduler/kubelet.",
                    recommendation="Ajustar request para ser menor ou igual ao limit.",
                    sources=(workload.source,),
                )

    # --- Métricas de runtime vs request (snapshot) ---
    if ctx.has_runtime_metrics:
        for workload in ctx.workloads:
            for snapshot in workload.metrics:
                for cm in snapshot.containers:
                    container_spec = next(
                        (c for c in workload.containers if c.name == cm.container_name),
                        None,
                    )
                    if not container_spec or not container_spec.cpu_request:
                        continue
                    if not cm.cpu_usage:
                        continue
                    usage = cm.cpu_usage.normalized_value
                    request = container_spec.cpu_request.normalized_value
                    if request <= 0:
                        continue
                    ratio = usage / request
                    if ratio < _CPU_USAGE_LOW_RATIO:
                        builder.add(
                            category="CPU",
                            severity=Severity.INFO,
                            confidence=Confidence.HIGH,
                            namespace=namespace,
                            workload=workload.name,
                            container=cm.container_name,
                            evidence=(
                                EvidenceItem(
                                    description="CPU usage (snapshot) muito abaixo do request",
                                    field_path=cm.cpu_usage.source.field_path,
                                    value=(
                                        f"usage={cm.cpu_usage.raw}, "
                                        f"request={container_spec.cpu_request.raw}"
                                    ),
                                    file_path=cm.cpu_usage.source.file_path,
                                    container=cm.container_name,
                                ),
                                EvidenceItem(
                                    description="Pod analisado",
                                    value=snapshot.pod_name,
                                    file_path=snapshot.source.file_path,
                                ),
                            ),
                            analysis=(
                                f"No snapshot coletado, o uso de CPU "
                                f"({format_cpu_millicores(usage)}) representa "
                                f"aproximadamente {ratio * 100:.1f}% do request configurado "
                                f"({container_spec.cpu_request.raw})."
                            ),
                            impact=(
                                "A configuração de request pode reservar CPU além do "
                                "necessário para este snapshot."
                            ),
                            recommendation=(
                                "Avaliar redução do CPU request com base em métricas "
                                "históricas antes de alterar produção."
                            ),
                            limitation=(
                                "Trata-se de snapshot pontual (PodMetrics), não de "
                                "série histórica de utilização."
                            ),
                            sources=(snapshot.source, workload.source),
                        )
    else:
        builder.add(
            category="CPU",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            namespace=namespace,
            analysis=(
                "A análise de utilização real de CPU não foi realizada devido à "
                "ausência de métricas de runtime (PodMetrics) nos dados disponíveis."
            ),
            limitation="Informação não disponível nos dados coletados.",
        )

    # --- Namespace vs pool allocatable (por nodeSelector dominante) ---
    selectors = {tuple(sorted(w.node_selector.items())) for w in ctx.workloads if w.node_selector}
    if not selectors:
        selectors = {()}

    for selector_tuple in selectors:
        selector = dict(selector_tuple)
        pool_nodes = matching_nodes(ctx.nodes, selector)
        pool_cpu = pool_cpu_allocatable_millicores(pool_nodes)
        if pool_cpu is None:
            continue

        ns_cpu = 0.0
        has_ns_cpu = False
        for workload in ctx.workloads:
            if selector and workload.node_selector != selector:
                continue
            total = workload_total_cpu_request_millicores(workload)
            if total is not None:
                ns_cpu += total
                has_ns_cpu = True

        if not has_ns_cpu or pool_cpu <= 0:
            continue

        ratio = ns_cpu / pool_cpu
        if ratio >= _NAMESPACE_CPU_POOL_HIGH_RATIO:
            sev = Severity.HIGH
        elif ratio >= _NAMESPACE_CPU_POOL_MEDIUM_RATIO:
            sev = Severity.MEDIUM
        else:
            continue

        selector_desc = (
            ", ".join(f"{k}={v}" for k, v in selector.items()) if selector else "(sem nodeSelector)"
        )
        builder.add(
            category="CPU",
            severity=sev,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="CPU request total do namespace (derivado)",
                    value=format_cpu_millicores(ns_cpu),
                ),
                EvidenceItem(
                    description="CPU allocatable do pool de nós compatível (derivado)",
                    value=format_cpu_millicores(pool_cpu),
                ),
                EvidenceItem(
                    description="Critério de pool",
                    value=f"nodeSelector: {selector_desc}; nós no pool: {len(pool_nodes)}",
                ),
            ),
            analysis=(
                f"Os requests de CPU do namespace somam {format_cpu_millicores(ns_cpu)}, "
                f"equivalente a {ratio * 100:.1f}% do allocatable ({format_cpu_millicores(pool_cpu)}) "
                f"do pool de {len(pool_nodes)} nó(s) compatível(is)."
            ),
            impact=(
                "Parcela significativa da capacidade reservável do pool está comprometida "
                "por requests deste namespace (pool compartilhado com outros namespaces)."
            ),
            recommendation=(
                "Revisar dimensionamento de CPU request e validar se o pool comporta "
                "crescimento de réplicas/HPA."
            ),
            limitation=(
                "Comparação baseada em requests configurados, não em uso real. "
                "O pool pode ser compartilhado por outros namespaces."
            ),
        )
