"""Análise de QoS."""

from __future__ import annotations

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity
from kubeoptix_core_ai.normalize.qos import QOS_BEST_EFFORT, QOS_BURSTABLE, QOS_GUARANTEED


def analyze_qos(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace

    for workload in ctx.workloads:
        qos = workload.qos_class
        if not qos:
            continue

        if qos == QOS_BEST_EFFORT:
            builder.add(
                category="QOS",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="QoS class observada ou derivada",
                        value=QOS_BEST_EFFORT,
                        file_path=workload.source.file_path,
                    ),
                ),
                analysis=(
                    f"O workload `{workload.name}` é classificado como BestEffort "
                    "(sem requests/limits em todos os recursos)."
                ),
                impact="Primeiro candidato a eviction em pressão de recursos no nó.",
                recommendation="Definir requests e limits adequados para workloads de produção.",
                sources=(workload.source,),
            )
        elif qos == QOS_GUARANTEED:
            builder.add(
                category="QOS",
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="QoS class",
                        value=QOS_GUARANTEED,
                        file_path=workload.source.file_path,
                    ),
                ),
                analysis=(
                    f"O workload `{workload.name}` é Guaranteed: request == limit "
                    "para CPU e memória em todos os containers."
                ),
                impact="Maior proteção contra eviction por recursos.",
                sources=(workload.source,),
            )
