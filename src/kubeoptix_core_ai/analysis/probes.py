"""Análise de probes."""

from __future__ import annotations

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity


def analyze_probes(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace

    for workload in ctx.workloads:
        replicas = workload.replicas_desired or 1
        for container in workload.containers:
            if container.readiness_probe is None:
                sev = Severity.HIGH if replicas >= 2 else Severity.MEDIUM
                builder.add(
                    category="PROBE",
                    severity=sev,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="readinessProbe ausente",
                            field_path="spec.template.spec.containers[].readinessProbe",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis=(
                        f"O container `{container.name}` não define readinessProbe."
                    ),
                    impact=(
                        "O Service pode encaminhar tráfego a pods não prontos."
                    ),
                    recommendation=(
                        "Adicionar readinessProbe HTTP/TCP adequada ao endpoint de saúde."
                    ),
                    sources=(workload.source,),
                )

            if container.liveness_probe is None:
                builder.add(
                    category="PROBE",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="livenessProbe ausente",
                            field_path="spec.template.spec.containers[].livenessProbe",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis=(
                        f"O container `{container.name}` não define livenessProbe."
                    ),
                    impact=(
                        "Processos travados podem não ser reiniciados automaticamente."
                    ),
                    recommendation="Adicionar livenessProbe para detectar deadlocks.",
                    sources=(workload.source,),
                )

            if container.startup_probe is None:
                builder.add(
                    category="PROBE",
                    severity=Severity.INFO,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="startupProbe ausente",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis=(
                        f"O container `{container.name}` não define startupProbe."
                    ),
                    impact=(
                        "Aplicações com inicialização lenta podem falhar liveness "
                        "prematuramente se configurada."
                    ),
                    recommendation=(
                        "Considerar startupProbe para apps com boot longo."
                    ),
                    sources=(workload.source,),
                )
