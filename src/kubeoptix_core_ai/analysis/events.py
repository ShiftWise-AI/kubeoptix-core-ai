"""Análise de Events do namespace (somente evidência coletada)."""

from __future__ import annotations

from collections import defaultdict

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity
from kubeoptix_core_ai.models.inventory import EventSpec

_HIGH_REASONS = frozenset(
    {
        "FailedGetResourceMetric",
        "FailedAttachVolume",
        "FailedMount",
        "FailedScheduling",
        "BackOff",
        "CrashLoopBackOff",
        "OOMKilling",
        "OOMKilled",
    }
)
_MEDIUM_REASONS = frozenset(
    {
        "Unhealthy",
        "ProbeWarning",
    }
)
_CRITICAL_REASONS = frozenset({"OOMKilling", "OOMKilled"})


def _event_count(event: EventSpec) -> int:
    return event.count if event.count is not None else 1


def _severity_for_reason(reason: str) -> Severity:
    if reason in _CRITICAL_REASONS:
        return Severity.CRITICAL
    if reason in _HIGH_REASONS:
        return Severity.HIGH
    if reason in _MEDIUM_REASONS:
        return Severity.MEDIUM
    return Severity.LOW


def analyze_events(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace
    warnings = [
        event
        for event in ctx.events
        if (event.event_type or "").lower() == "warning" and event.reason
    ]
    if not warnings:
        return

    grouped: dict[tuple[str, str, str], list[EventSpec]] = defaultdict(list)
    for event in warnings:
        key = (
            event.reason or "Unknown",
            event.involved_kind or "—",
            event.involved_name or "—",
        )
        grouped[key].append(event)

    for (reason, kind, name), events in sorted(grouped.items()):
        total_count = sum(_event_count(event) for event in events)
        sample = events[0]
        workload = name if kind in {"Pod", "ReplicaSet", "Deployment", "HorizontalPodAutoscaler", "StatefulSet"} else None
        message = (sample.message or "").replace("\n", " ")
        if len(message) > 220:
            message = message[:217] + "..."

        builder.add(
            category="EVENT",
            severity=_severity_for_reason(reason),
            confidence=Confidence.HIGH,
            namespace=namespace,
            workload=workload,
            evidence=(
                EvidenceItem(
                    description="Evento Warning agregado",
                    value=(
                        f"reason={reason}, involved={kind}/{name}, "
                        f"ocorrências={total_count}, arquivos={len(events)}"
                    ),
                    file_path=sample.source.file_path,
                ),
                EvidenceItem(
                    description="Mensagem (amostra)",
                    value=message or "—",
                    file_path=sample.source.file_path,
                ),
            ),
            analysis=(
                f"{len(events)} Evento(s) Warning `{reason}` em `{kind}/{name}` "
                f"(contagem acumulada {total_count})."
            ),
            impact=_impact_for_reason(reason),
            recommendation=_recommendation_for_reason(reason),
            limitation=(
                "Snapshot de Events do dump; sem série temporal nem garantia "
                "de que o problema persiste."
            ),
            sources=(sample.source,),
        )


def _impact_for_reason(reason: str) -> str:
    if reason in {"FailedGetResourceMetric"}:
        return "HPA pode não escalar por falta de métrica de CPU/memória."
    if reason in {"FailedAttachVolume", "FailedMount"}:
        return "Pod pode permanecer Pending/não pronto por falha de volume."
    if reason in {"Unhealthy"}:
        return "Probe de saúde falhou; tráfego ou reinícios podem ser afetados."
    if reason in {"BackOff", "CrashLoopBackOff"}:
        return "Container não permanece em execução."
    if reason in _CRITICAL_REASONS:
        return "Processo encerrado por falta de memória."
    return "Evento Warning observado no namespace."


def _recommendation_for_reason(reason: str) -> str:
    if reason == "FailedGetResourceMetric":
        return "Definir CPU/memory request no container alvo do HPA."
    if reason in {"FailedAttachVolume", "FailedMount"}:
        return "Verificar PVC, StorageClass e se o volume está montado em um único nó."
    if reason == "Unhealthy":
        return "Ajustar probes (path, timeout, initialDelay) com base na falha observada."
    if reason in {"BackOff", "CrashLoopBackOff"}:
        return "Inspecionar logs do container e causa do exit code."
    if reason in _CRITICAL_REASONS:
        return "Aumentar memory limit/request após validar o uso real."
    return "Investigar o Evento Warning no namespace."
