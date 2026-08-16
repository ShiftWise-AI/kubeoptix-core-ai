"""Enriquecimento e agregação de workloads normalizados."""

from __future__ import annotations

from kubeoptix_core_ai.models.workload import ContainerSpec, Workload
from kubeoptix_core_ai.normalize.qos import classify_qos


def aggregate_container_requests(
    containers: tuple[ContainerSpec, ...],
) -> tuple[float | None, float | None]:
    """Soma requests de CPU (millicores) e memória (bytes) por pod."""
    cpu_total = 0.0
    mem_total = 0.0
    has_cpu = False
    has_mem = False

    for container in containers:
        if container.cpu_request is not None:
            cpu_total += container.cpu_request.normalized_value
            has_cpu = True
        if container.memory_request is not None:
            mem_total += container.memory_request.normalized_value
            has_mem = True

    return (
        cpu_total if has_cpu else None,
        mem_total if has_mem else None,
    )


def enrich_workload(workload: Workload) -> Workload:
    """Calcula campos derivados (QoS, totais de request por pod)."""
    cpu_total, mem_total = aggregate_container_requests(workload.containers)
    qos = workload.qos_class or classify_qos(workload.containers)

    return workload.model_copy(
        update={
            "qos_class": qos,
            "total_cpu_request_per_pod_millicores": cpu_total,
            "total_memory_request_per_pod_bytes": mem_total,
        }
    )
