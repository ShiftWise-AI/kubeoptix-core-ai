"""Utilitários compartilhados da camada de análise."""

from __future__ import annotations

from collections import Counter

from kubeoptix_analyzer.models.node import WorkNode
from kubeoptix_analyzer.models.workload import Workload


def format_cpu_millicores(value: float) -> str:
    if value == int(value):
        return f"{int(value)}m"
    return f"{value:.2f}m"


def format_memory_bytes(value: float) -> str:
    mib = value / (1024**2)
    if abs(mib - round(mib)) < 0.01:
        return f"{int(round(mib))}Mi"
    return f"{mib:.2f}Mi"


def node_matches_selector(node: WorkNode, selector: dict[str, str]) -> bool:
    if not selector:
        return True
    return all(node.labels.get(k) == v for k, v in selector.items())


def matching_nodes(nodes: tuple[WorkNode, ...], selector: dict[str, str]) -> tuple[WorkNode, ...]:
    if not selector:
        return nodes
    return tuple(n for n in nodes if node_matches_selector(n, selector))


def derive_scheduling_pool_selector(workloads: tuple[Workload, ...]) -> dict[str, str]:
    """
    Retorna o nodeSelector do pool de scheduling relevante.

    Quando workloads divergem (ex.: frontend sem selector, backends com
    ``env=prd,type=app``), usa o selector majoritário entre workloads que
    definem nodeSelector — não o pool inteiro do cluster.
    """
    selectors = [w.node_selector for w in workloads if w.node_selector]
    if not selectors:
        return {}
    ranked = Counter(tuple(sorted(s.items())) for s in selectors)
    return dict(ranked.most_common(1)[0][0])


def node_role_label(node: WorkNode) -> str:
    """Descrição curta do papel do nó para tabelas de placement."""
    parts: list[str] = []
    if node.role:
        parts.append(node.role)
    if node.env:
        parts.append(node.env)
    if parts:
        return "/".join(parts)
    return "—"


def aggregate_runtime_usage(workloads: tuple[Workload, ...]) -> tuple[float | None, float | None]:
    """Soma CPU usage (millicores) e memória usage (bytes) de todos os PodMetrics."""
    cpu_total = 0.0
    mem_total = 0.0
    has_cpu = False
    has_mem = False
    for workload in workloads:
        for snapshot in workload.metrics:
            for cm in snapshot.containers:
                if cm.cpu_usage is not None:
                    cpu_total += cm.cpu_usage.normalized_value
                    has_cpu = True
                if cm.memory_usage is not None:
                    mem_total += cm.memory_usage.normalized_value
                    has_mem = True
    return (cpu_total if has_cpu else None, mem_total if has_mem else None)


def pool_cpu_allocatable_millicores(nodes: tuple[WorkNode, ...]) -> float | None:
    total = 0.0
    has_any = False
    for node in nodes:
        if node.cpu_allocatable is None:
            return None
        total += node.cpu_allocatable.normalized_value
        has_any = True
    return total if has_any else None


def pool_memory_allocatable_bytes(nodes: tuple[WorkNode, ...]) -> float | None:
    total = 0.0
    has_any = False
    for node in nodes:
        if node.memory_allocatable is None:
            return None
        total += node.memory_allocatable.normalized_value
        has_any = True
    return total if has_any else None


def workload_total_cpu_request_millicores(workload: Workload) -> float | None:
    if workload.total_cpu_request_per_pod_millicores is None:
        return None
    if workload.replicas_desired is None:
        return None
    return workload.total_cpu_request_per_pod_millicores * workload.replicas_desired


def workload_total_memory_request_bytes(workload: Workload) -> float | None:
    if workload.total_memory_request_per_pod_bytes is None:
        return None
    if workload.replicas_desired is None:
        return None
    return workload.total_memory_request_per_pod_bytes * workload.replicas_desired


def has_pod_anti_affinity(workload: Workload) -> bool:
    affinity = workload.affinity or {}
    pod_anti = affinity.get("podAntiAffinity")
    if not pod_anti:
        return False
    required = pod_anti.get("requiredDuringSchedulingIgnoredDuringExecution") or []
    preferred = pod_anti.get("preferredDuringSchedulingIgnoredDuringExecution") or []
    return bool(required or preferred)


def has_custom_tolerations(workload: Workload) -> bool:
    """Tolerations além das default do Kubernetes."""
    if not workload.tolerations:
        return False
    for tol in workload.tolerations:
        key = str(tol.get("key", ""))
        if key.startswith("node.kubernetes.io"):
            continue
        return True
    return False
