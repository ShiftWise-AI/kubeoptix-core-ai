"""Análise de scheduling."""

from __future__ import annotations

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.analysis.helpers import has_custom_tolerations, has_pod_anti_affinity, matching_nodes
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity


def analyze_scheduling(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace

    workloads_with_selector = [w for w in ctx.workloads if w.node_selector]
    workloads_without_selector = [w for w in ctx.workloads if not w.node_selector]

    if workloads_with_selector and workloads_without_selector:
        names_with = ", ".join(w.name for w in workloads_with_selector)
        names_without = ", ".join(w.name for w in workloads_without_selector)
        builder.add(
            category="SCHED",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="Workloads com nodeSelector",
                    value=names_with,
                ),
                EvidenceItem(
                    description="Workloads sem nodeSelector",
                    value=names_without,
                ),
            ),
            analysis=(
                "Há workloads com e sem nodeSelector no mesmo namespace, "
                "o que pode levar a agendamento em pools de nós diferentes."
            ),
            impact=(
                "Réplicas sem nodeSelector podem ser alocadas em nós de outros papéis "
                "(ex.: infra/router), conforme evidência de placement."
            ),
            recommendation=(
                "Alinhar nodeSelector entre workloads do mesmo namespace quando "
                "apropriado."
            ),
        )

    for workload in ctx.workloads:
        if workload.node_selector:
            pool = matching_nodes(ctx.nodes, workload.node_selector)
            if not pool:
                builder.add(
                    category="SCHED",
                    severity=Severity.CRITICAL,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="nodeSelector sem nós compatíveis",
                            value=str(workload.node_selector),
                            field_path="spec.template.spec.nodeSelector",
                            file_path=workload.source.file_path,
                        ),
                    ),
                    analysis=(
                        f"Nenhum worknode nos dados coletados satisfaz o nodeSelector "
                        f"{workload.node_selector}."
                    ),
                    impact="Pods podem permanecer Pending por impossibilidade de scheduling.",
                    recommendation="Revisar labels dos nós ou o nodeSelector do workload.",
                    sources=(workload.source,),
                )

        replicas = workload.replicas_desired or 0
        if replicas >= 2 and not has_pod_anti_affinity(workload):
            builder.add(
                category="SCHED",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="podAntiAffinity ausente",
                        field_path="spec.template.spec.affinity.podAntiAffinity",
                        file_path=workload.source.file_path,
                    ),
                    EvidenceItem(
                        description="Réplicas desejadas",
                        value=str(replicas),
                        field_path="spec.replicas",
                    ),
                ),
                analysis=(
                    f"O workload `{workload.name}` possui {replicas} réplicas sem "
                    "podAntiAffinity configurada."
                ),
                impact=(
                    "Réplicas podem concentrar-se no mesmo nó, reduzindo resiliência "
                    "a falha de nó."
                ),
                recommendation=(
                    "Adicionar podAntiAffinity (preferred ou required) por hostname."
                ),
                sources=(workload.source,),
            )

        if not workload.topology_spread_constraints and replicas >= 2:
            builder.add(
                category="SCHED",
                severity=Severity.INFO,
                confidence=Confidence.MEDIUM,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="topologySpreadConstraints ausente",
                        file_path=workload.source.file_path,
                    ),
                ),
                analysis=(
                    f"`{workload.name}` não define topologySpreadConstraints."
                ),
                recommendation=(
                    "Considerar topologySpreadConstraints para distribuição uniforme."
                ),
                sources=(workload.source,),
            )

        if has_custom_tolerations(workload):
            builder.add(
                category="SCHED",
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="tolerations customizadas configuradas",
                        file_path=workload.source.file_path,
                    ),
                ),
                analysis="O workload define tolerations além das padrão do Kubernetes.",
                impact="Pode ser agendado em nós com taints correspondentes.",
                sources=(workload.source,),
            )
