"""Agregação de métricas de diagnóstico de ingestão."""

from __future__ import annotations

from kubeoptix_analyzer.models.diagnostic import (
    ContainerResourceEntry,
    ResourceTotals,
    WorkloadDiagnosticSummary,
    WorknodeDiagnosticSummary,
)
from kubeoptix_analyzer.models.node import WorkNode
from kubeoptix_analyzer.models.quantities import ResourceQuantity
from kubeoptix_analyzer.models.workload import Workload


def _format_cpu_millicores(value: float) -> str:
    if value == int(value):
        return f"{int(value)}m"
    return f"{value:.2f}m"


def _format_memory_bytes(value: float) -> str:
    mib = value / (1024**2)
    if abs(mib - round(mib)) < 0.01:
        return f"{int(round(mib))}Mi"
    return f"{mib:.2f}Mi"


def _entries_from_workloads(
    workloads: tuple[Workload, ...],
    attr: str,
) -> tuple[ContainerResourceEntry, ...]:
    entries: list[ContainerResourceEntry] = []
    for workload in workloads:
        for container in workload.containers:
            qty: ResourceQuantity | None = getattr(container, attr)
            if qty is None:
                continue
            entries.append(
                ContainerResourceEntry(
                    workload=workload.name,
                    container=container.name,
                    value_raw=qty.raw,
                    field_path=qty.source.field_path,
                    file_path=qty.source.file_path,
                )
            )
    return tuple(entries)


def _sum_per_pod_times_replicas(
    workloads: tuple[Workload, ...],
    attr: str,
) -> tuple[float | None, str | None]:
    """
    Soma (valor por pod × réplicas desejadas) para cada workload.

    Retorna (total_normalizado, nota) — nota preenchida quando há lacunas.
    """
    total = 0.0
    has_any = False
    missing_replicas: list[str] = []
    missing_values: list[str] = []

    for workload in workloads:
        per_pod = 0.0
        pod_has_value = False
        for container in workload.containers:
            qty: ResourceQuantity | None = getattr(container, attr)
            if qty is not None:
                per_pod += qty.normalized_value
                pod_has_value = True

        if not pod_has_value:
            missing_values.append(workload.name)
            continue

        if workload.replicas_desired is None:
            missing_replicas.append(workload.name)
            continue

        total += per_pod * workload.replicas_desired
        has_any = True

    if not has_any:
        return None, "Nenhum valor disponível nos dados coletados"

    notes: list[str] = []
    if missing_replicas:
        notes.append(
            "réplicas indisponíveis para: " + ", ".join(sorted(missing_replicas))
        )
    if missing_values:
        notes.append(
            "valores indisponíveis para: " + ", ".join(sorted(missing_values))
        )

    note = "; ".join(notes) if notes else None
    return total, note


def _resource_totals(
    workloads: tuple[Workload, ...],
    attr: str,
    *,
    resource_kind: str,
) -> ResourceTotals:
    entries = _entries_from_workloads(workloads, attr)
    total, note = _sum_per_pod_times_replicas(workloads, attr)

    if total is None:
        return ResourceTotals(
            available=False,
            display="indisponível",
            note=note,
            entries=entries,
        )

    if resource_kind == "cpu":
        display = _format_cpu_millicores(total)
    else:
        display = _format_memory_bytes(total)

    return ResourceTotals(
        available=True,
        total_normalized=total,
        display=display,
        note=note,
        entries=entries,
    )


def summarize_workloads(workloads: tuple[Workload, ...]) -> WorkloadDiagnosticSummary:
    container_count = sum(len(w.containers) for w in workloads)

    missing_replicas = [w for w in workloads if w.replicas_desired is None]
    if missing_replicas:
        replicas_total = None
    else:
        replicas_total = sum(w.replicas_desired for w in workloads)

    return WorkloadDiagnosticSummary(
        workload_count=len(workloads),
        container_count=container_count,
        replicas_desired_total=replicas_total,
        replicas_unavailable_count=len(missing_replicas),
        cpu_requests=_resource_totals(workloads, "cpu_request", resource_kind="cpu"),
        cpu_limits=_resource_totals(workloads, "cpu_limit", resource_kind="cpu"),
        memory_requests=_resource_totals(workloads, "memory_request", resource_kind="memory"),
        memory_limits=_resource_totals(workloads, "memory_limit", resource_kind="memory"),
    )


def _sum_node_quantities(
    nodes: tuple[WorkNode, ...],
    attr: str,
) -> ResourceTotals:
    entries: list[ContainerResourceEntry] = []
    total = 0.0
    missing: list[str] = []

    for node in nodes:
        qty: ResourceQuantity | None = getattr(node, attr)
        if qty is None:
            missing.append(node.name)
            continue
        total += qty.normalized_value
        entries.append(
            ContainerResourceEntry(
                workload=node.name,
                container="(nó)",
                value_raw=qty.raw,
                field_path=qty.source.field_path,
                file_path=qty.source.file_path,
            )
        )

    if not entries:
        return ResourceTotals(
            available=False,
            display="indisponível",
            note="Nenhum valor disponível nos dados coletados",
            entries=(),
        )

    is_cpu = attr.startswith("cpu")
    display = (
        _format_cpu_millicores(total)
        if is_cpu
        else _format_memory_bytes(total)
    )

    note = None
    if missing:
        note = "valores indisponíveis para nós: " + ", ".join(sorted(missing))

    return ResourceTotals(
        available=True,
        total_normalized=total,
        display=display,
        note=note,
        entries=tuple(entries),
    )


def summarize_worknodes(
    nodes: tuple[WorkNode, ...],
    parse_errors: tuple[str, ...] = (),
) -> WorknodeDiagnosticSummary:
    return WorknodeDiagnosticSummary(
        worknode_count=len(nodes),
        cpu_capacity=_sum_node_quantities(nodes, "cpu_capacity"),
        cpu_allocatable=_sum_node_quantities(nodes, "cpu_allocatable"),
        memory_capacity=_sum_node_quantities(nodes, "memory_capacity"),
        memory_allocatable=_sum_node_quantities(nodes, "memory_allocatable"),
        parse_errors=parse_errors,
    )
