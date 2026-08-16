"""Normalização de quantidades e workloads."""

from kubeoptix_analyzer.normalize.quantities import (
    parse_cpu_quantity,
    parse_memory_quantity,
)
from kubeoptix_analyzer.normalize.qos import classify_qos
from kubeoptix_analyzer.normalize.workload import (
    aggregate_container_requests,
    enrich_workload,
)

__all__ = [
    "aggregate_container_requests",
    "classify_qos",
    "enrich_workload",
    "parse_cpu_quantity",
    "parse_memory_quantity",
]
