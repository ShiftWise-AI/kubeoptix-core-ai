"""Extração de datasets numéricos a partir do assessment."""

from __future__ import annotations

from kubeoptix_core_ai.analysis.helpers import (
    derive_scheduling_pool_selector,
    format_cpu_millicores,
    format_memory_bytes,
    matching_nodes,
    pool_cpu_allocatable_millicores,
    pool_memory_allocatable_bytes,
)
from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.models import ChartDataset, ChartPoint, ChartSeries
from kubeoptix_core_ai.visualization.provenance import calculated, from_field_ref
from kubeoptix_core_ai.models.workload import Workload


def _workload_cpu_request_m(workload: Workload) -> float | None:
    if workload.total_cpu_request_per_pod_millicores is None:
        return None
    return workload.total_cpu_request_per_pod_millicores


def _workload_cpu_limit_m(workload: Workload) -> float | None:
    total = 0.0
    has_any = False
    for container in workload.containers:
        if container.cpu_limit is not None:
            total += container.cpu_limit.normalized_value
            has_any = True
    return total if has_any else None


def _workload_mem_request_bytes(workload: Workload) -> float | None:
    return workload.total_memory_request_per_pod_bytes


def _workload_mem_limit_bytes(workload: Workload) -> float | None:
    total = 0.0
    has_any = False
    for container in workload.containers:
        if container.memory_limit is not None:
            total += container.memory_limit.normalized_value
            has_any = True
    return total if has_any else None


def _cpu_provenance(workload: Workload, attr: str) -> tuple:
    refs = []
    for container in workload.containers:
        qty = getattr(container, attr)
        if qty is not None:
            refs.append(from_field_ref(qty.source))
    return tuple(refs)


def _mem_provenance(workload: Workload, attr: str) -> tuple:
    return _cpu_provenance(workload, attr)


def build_cpu_request_chart(bundle: AssessmentBundle) -> ChartDataset | None:
    workloads = bundle.context.workloads
    points: list[ChartPoint] = []
    labels: list[str] = []
    for wl in workloads:
        value = _workload_cpu_request_m(wl)
        if value is None:
            continue
        labels.append(wl.name)
        points.append(
            ChartPoint(
                label=wl.name,
                value=value,
                unit="m",
                provenance=_cpu_provenance(wl, "cpu_request"),
            )
        )
    if not points:
        return None
    return ChartDataset(
        title="CPU request por workload (por pod)",
        question="Quanto de CPU cada workload reserva por pod?",
        x_labels=tuple(labels),
        y_axis_label="CPU (millicores)",
        x_axis_label="Workload",
        series=(
            ChartSeries(
                name="CPU request",
                points=tuple(points),
                series_type="bar",
            ),
        ),
    )


def build_cpu_limit_chart(bundle: AssessmentBundle) -> ChartDataset | None:
    workloads = bundle.context.workloads
    points: list[ChartPoint] = []
    labels: list[str] = []
    for wl in workloads:
        value = _workload_cpu_limit_m(wl)
        if value is None:
            continue
        labels.append(wl.name)
        points.append(
            ChartPoint(
                label=wl.name,
                value=value,
                unit="m",
                provenance=_cpu_provenance(wl, "cpu_limit"),
            )
        )
    if not points:
        return None
    return ChartDataset(
        title="CPU limit por workload (por pod)",
        question="Qual o teto de CPU configurado por pod em cada workload?",
        x_labels=tuple(labels),
        y_axis_label="CPU (millicores)",
        x_axis_label="Workload",
        series=(
            ChartSeries(
                name="CPU limit",
                points=tuple(points),
                series_type="bar",
            ),
        ),
    )


def build_memory_request_chart(bundle: AssessmentBundle) -> ChartDataset | None:
    workloads = bundle.context.workloads
    points: list[ChartPoint] = []
    labels: list[str] = []
    for wl in workloads:
        value = _workload_mem_request_bytes(wl)
        if value is None:
            continue
        labels.append(wl.name)
        points.append(
            ChartPoint(
                label=wl.name,
                value=value / (1024**2),
                unit="Mi",
                provenance=_mem_provenance(wl, "memory_request"),
            )
        )
    if not points:
        return None
    return ChartDataset(
        title="Memória request por workload (por pod)",
        question="Quanto de memória cada workload reserva por pod?",
        x_labels=tuple(labels),
        y_axis_label="Memória (MiB)",
        x_axis_label="Workload",
        series=(
            ChartSeries(
                name="Mem request",
                points=tuple(points),
                series_type="bar",
            ),
        ),
    )


def build_memory_limit_chart(bundle: AssessmentBundle) -> ChartDataset | None:
    workloads = bundle.context.workloads
    points: list[ChartPoint] = []
    labels: list[str] = []
    for wl in workloads:
        value = _workload_mem_limit_bytes(wl)
        if value is None:
            continue
        labels.append(wl.name)
        points.append(
            ChartPoint(
                label=wl.name,
                value=value / (1024**2),
                unit="Mi",
                provenance=_mem_provenance(wl, "memory_limit"),
            )
        )
    if not points:
        return None
    return ChartDataset(
        title="Memória limit por workload (por pod)",
        question="Qual o teto de memória configurado por pod em cada workload?",
        x_labels=tuple(labels),
        y_axis_label="Memória (MiB)",
        x_axis_label="Workload",
        series=(
            ChartSeries(
                name="Mem limit",
                points=tuple(points),
                series_type="bar",
            ),
        ),
    )


def build_cpu_request_limit_chart(bundle: AssessmentBundle) -> ChartDataset | None:
    workloads = bundle.context.workloads
    request_points: list[ChartPoint] = []
    limit_points: list[ChartPoint] = []
    labels: list[str] = []
    for wl in workloads:
        req = _workload_cpu_request_m(wl)
        lim = _workload_cpu_limit_m(wl)
        if req is None and lim is None:
            continue
        labels.append(wl.name)
        request_points.append(
            ChartPoint(
                label=wl.name,
                value=req or 0.0,
                unit="m",
                provenance=_cpu_provenance(wl, "cpu_request"),
            )
        )
        limit_points.append(
            ChartPoint(
                label=wl.name,
                value=lim or 0.0,
                unit="m",
                provenance=_cpu_provenance(wl, "cpu_limit"),
            )
        )
    if not labels:
        return None
    return ChartDataset(
        title="CPU request × limit por workload (por pod)",
        question="Como request e limit de CPU se comparam em cada workload?",
        x_labels=tuple(labels),
        y_axis_label="CPU (millicores)",
        x_axis_label="Workload",
        series=(
            ChartSeries(name="Request", points=tuple(request_points), series_type="bar"),
            ChartSeries(name="Limit", points=tuple(limit_points), series_type="bar"),
        ),
    )


def build_memory_request_limit_chart(bundle: AssessmentBundle) -> ChartDataset | None:
    workloads = bundle.context.workloads
    request_points: list[ChartPoint] = []
    limit_points: list[ChartPoint] = []
    labels: list[str] = []
    for wl in workloads:
        req = _workload_mem_request_bytes(wl)
        lim = _workload_mem_limit_bytes(wl)
        if req is None and lim is None:
            continue
        labels.append(wl.name)
        request_points.append(
            ChartPoint(
                label=wl.name,
                value=(req or 0.0) / (1024**2),
                unit="Mi",
                provenance=_mem_provenance(wl, "memory_request"),
            )
        )
        limit_points.append(
            ChartPoint(
                label=wl.name,
                value=(lim or 0.0) / (1024**2),
                unit="Mi",
                provenance=_mem_provenance(wl, "memory_limit"),
            )
        )
    if not labels:
        return None
    return ChartDataset(
        title="Memória request × limit por workload (por pod)",
        question="Como request e limit de memória se comparam em cada workload?",
        x_labels=tuple(labels),
        y_axis_label="Memória (MiB)",
        x_axis_label="Workload",
        series=(
            ChartSeries(name="Request", points=tuple(request_points), series_type="bar"),
            ChartSeries(name="Limit", points=tuple(limit_points), series_type="bar"),
        ),
    )


def build_namespace_requests_vs_allocatable(bundle: AssessmentBundle) -> ChartDataset | None:
    workloads = bundle.context.workloads
    nodes = bundle.context.nodes
    wl_diag = bundle.diagnostic.workloads

    selector = derive_scheduling_pool_selector(workloads)
    pool_nodes = matching_nodes(nodes, selector)
    pool_cpu = pool_cpu_allocatable_millicores(pool_nodes)
    pool_mem = pool_memory_allocatable_bytes(pool_nodes)

    cpu_req = wl_diag.cpu_requests.total_normalized
    mem_req = wl_diag.memory_requests.total_normalized

    labels: list[str] = []
    request_vals: list[float] = []
    capacity_vals: list[float] = []
    provenance: list = []

    if cpu_req is not None and pool_cpu is not None:
        labels.append("CPU")
        request_vals.append(cpu_req)
        capacity_vals.append(pool_cpu)
        provenance.append(
            calculated(
                f"CPU request namespace: {wl_diag.cpu_requests.display}; "
                f"allocatable pool: {format_cpu_millicores(pool_cpu)}",
            )
        )

    if mem_req is not None and pool_mem is not None:
        labels.append("Memória")
        request_vals.append(mem_req / (1024**2))
        capacity_vals.append(pool_mem / (1024**2))
        provenance.append(
            calculated(
                f"Mem request namespace: {wl_diag.memory_requests.display}; "
                f"allocatable pool: {format_memory_bytes(pool_mem)}",
            )
        )

    if not labels:
        return None

    request_points = tuple(
        ChartPoint(label=label, value=val, unit="", provenance=(prov,))
        for label, val, prov in zip(labels, request_vals, provenance)
    )
    capacity_points = tuple(
        ChartPoint(label=label, value=val, unit="", provenance=(prov,))
        for label, val, prov in zip(labels, capacity_vals, provenance)
    )

    y_label = "CPU (m) / Memória (MiB)"
    return ChartDataset(
        title="Requests do namespace × capacidade allocatable do pool",
        question="Os requests agregados do namespace cabem no pool de scheduling relevante?",
        x_labels=tuple(labels),
        y_axis_label=y_label,
        x_axis_label="Recurso",
        series=(
            ChartSeries(name="Request namespace", points=request_points, series_type="bar"),
            ChartSeries(name="Allocatable pool", points=capacity_points, series_type="bar"),
        ),
    )
