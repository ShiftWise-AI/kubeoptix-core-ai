"""Análise de requests e limits (relações gerais)."""

from __future__ import annotations

from kubeoptix_analyzer.analysis.context import AnalysisContext
from kubeoptix_analyzer.analysis.findings_builder import FindingBuilder
from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Severity

# Limit/request < 1.5x pode indicar pouca margem para bursts
_LOW_HEADROOM_RATIO = 1.5


def analyze_resources(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace

    for workload in ctx.workloads:
        for container in workload.containers:
            # CPU headroom
            if (
                container.cpu_request is not None
                and container.cpu_limit is not None
                and container.cpu_request.normalized_value > 0
            ):
                ratio = (
                    container.cpu_limit.normalized_value
                    / container.cpu_request.normalized_value
                )
                if ratio < _LOW_HEADROOM_RATIO:
                    builder.add(
                        category="RES",
                        severity=Severity.LOW,
                        confidence=Confidence.HIGH,
                        namespace=namespace,
                        workload=workload.name,
                        container=container.name,
                        evidence=(
                            EvidenceItem(
                                description="Relação CPU limit/request baixa",
                                value=(
                                    f"request={container.cpu_request.raw}, "
                                    f"limit={container.cpu_limit.raw}, "
                                    f"ratio={ratio:.2f}"
                                ),
                                file_path=container.cpu_request.source.file_path,
                                field_path=container.cpu_limit.source.field_path,
                                container=container.name,
                            ),
                        ),
                        analysis=(
                            f"CPU limit ({container.cpu_limit.raw}) é menos de "
                            f"{_LOW_HEADROOM_RATIO}x o request ({container.cpu_request.raw})."
                        ),
                        impact="Pouca margem entre request e limit para picos de CPU.",
                        recommendation=(
                            "Avaliar se o limit oferece folga suficiente para bursts."
                        ),
                        sources=(workload.source,),
                    )

            # Memória headroom
            if (
                container.memory_request is not None
                and container.memory_limit is not None
                and container.memory_request.normalized_value > 0
            ):
                ratio = (
                    container.memory_limit.normalized_value
                    / container.memory_request.normalized_value
                )
                if ratio < _LOW_HEADROOM_RATIO:
                    builder.add(
                        category="RES",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.HIGH,
                        namespace=namespace,
                        workload=workload.name,
                        container=container.name,
                        evidence=(
                            EvidenceItem(
                                description="Relação memória limit/request baixa",
                                value=(
                                    f"request={container.memory_request.raw}, "
                                    f"limit={container.memory_limit.raw}, "
                                    f"ratio={ratio:.2f}"
                                ),
                                file_path=container.memory_request.source.file_path,
                                container=container.name,
                            ),
                        ),
                        analysis=(
                            f"Memory limit ({container.memory_limit.raw}) é menos de "
                            f"{_LOW_HEADROOM_RATIO}x o request ({container.memory_request.raw})."
                        ),
                        impact=(
                            "Risco de throttling/OOM do container em picos de memória "
                            "(não comprovado sem eventos de runtime)."
                        ),
                        recommendation="Revisar limit de memória considerando picos esperados.",
                        limitation="OOMKilled não inferido sem evidência de eventos.",
                        sources=(workload.source,),
                    )

            # Request sem limit ou limit sem request
            has_cpu_req = container.cpu_request is not None
            has_cpu_lim = container.cpu_limit is not None
            if has_cpu_req != has_cpu_lim:
                builder.add(
                    category="RES",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="Configuração assimétrica de CPU",
                            value=f"request={'sim' if has_cpu_req else 'não'}, limit={'sim' if has_cpu_lim else 'não'}",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis="CPU request e limit não estão ambos definidos.",
                    impact="Pode resultar em QoS Burstable parcial ou comportamento inesperado.",
                    recommendation="Definir request e limit de forma consistente.",
                    sources=(workload.source,),
                )

            has_mem_req = container.memory_request is not None
            has_mem_lim = container.memory_limit is not None
            if has_mem_req != has_mem_lim:
                builder.add(
                    category="RES",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    container=container.name,
                    evidence=(
                        EvidenceItem(
                            description="Configuração assimétrica de memória",
                            value=f"request={'sim' if has_mem_req else 'não'}, limit={'sim' if has_mem_lim else 'não'}",
                            file_path=workload.source.file_path,
                            container=container.name,
                        ),
                    ),
                    analysis="Memory request e limit não estão ambos definidos.",
                    recommendation="Definir request e limit de memória de forma consistente.",
                    sources=(workload.source,),
                )
