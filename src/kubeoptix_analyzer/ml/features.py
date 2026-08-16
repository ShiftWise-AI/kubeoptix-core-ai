"""Extração de features numéricas estruturadas por workload.

Cada feature resolve um aspecto comparável entre workloads do mesmo namespace.
Não usamos embeddings textuais: os dados são quantitativos e já normalizados
na camada de ingestão (requests, limits, réplicas, flags de configuração).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from kubeoptix_analyzer.analysis.helpers import has_pod_anti_affinity
from kubeoptix_analyzer.models.workload import Workload

# Ordem fixa das colunas — necessária para reprodutibilidade e testes.
FEATURE_NAMES: tuple[str, ...] = (
    "cpu_request_m",
    "mem_request_mib",
    "cpu_limit_m",
    "mem_limit_mib",
    "replicas",
    "container_count",
    "cpu_limit_request_ratio",
    "mem_limit_request_ratio",
    "readiness_probe_ratio",
    "liveness_probe_ratio",
    "node_selector_flag",
    "anti_affinity_flag",
    "cpu_usage_request_ratio",
    "mem_usage_request_ratio",
)

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "cpu_request_m": "CPU request total por pod (millicores)",
    "mem_request_mib": "Memória request total por pod (MiB)",
    "cpu_limit_m": "CPU limit total por pod (millicores)",
    "mem_limit_mib": "Memória limit total por pod (MiB)",
    "replicas": "Réplicas desejadas do workload",
    "container_count": "Número de containers no pod template",
    "cpu_limit_request_ratio": "Razão CPU limit/request (por pod)",
    "mem_limit_request_ratio": "Razão memória limit/request (por pod)",
    "readiness_probe_ratio": "Fração de containers com readiness probe",
    "liveness_probe_ratio": "Fração de containers com liveness probe",
    "node_selector_flag": "1 se nodeSelector configurado, senão 0",
    "anti_affinity_flag": "1 se podAntiAffinity configurado, senão 0",
    "cpu_usage_request_ratio": "Média usage/request de CPU (PodMetrics); NaN se ausente",
    "mem_usage_request_ratio": "Média usage/request de memória (PodMetrics); NaN se ausente",
}


@dataclass(frozen=True)
class FeatureMatrix:
    """Matriz de features por workload do namespace."""

    workload_names: tuple[str, ...]
    matrix: np.ndarray  # shape (n_workloads, n_features)
    feature_names: tuple[str, ...] = FEATURE_NAMES

    @property
    def workload_count(self) -> int:
        return len(self.workload_names)


def _sum_container_limits_millicores(workload: Workload) -> float:
    total = 0.0
    for container in workload.containers:
        if container.cpu_limit is not None:
            total += container.cpu_limit.normalized_value
    return total


def _sum_container_limits_bytes(workload: Workload) -> float:
    total = 0.0
    for container in workload.containers:
        if container.memory_limit is not None:
            total += container.memory_limit.normalized_value
    return total


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _probe_ratio(workload: Workload, probe_attr: str) -> float:
    if not workload.containers:
        return 0.0
    with_probe = sum(
        1 for c in workload.containers if getattr(c, probe_attr) is not None
    )
    return with_probe / len(workload.containers)


def _avg_usage_request_ratio(
    workload: Workload,
    *,
    resource: str,
) -> float:
    """Média de usage/request por container com métricas e request definidos."""
    ratios: list[float] = []
    for snapshot in workload.metrics:
        for cm in snapshot.containers:
            container_spec = next(
                (c for c in workload.containers if c.name == cm.container_name),
                None,
            )
            if container_spec is None:
                continue
            if resource == "cpu":
                request = container_spec.cpu_request
                usage = cm.cpu_usage
            else:
                request = container_spec.memory_request
                usage = cm.memory_usage
            if request is None or usage is None:
                continue
            req_val = request.normalized_value
            if req_val <= 0:
                continue
            ratios.append(usage.normalized_value / req_val)
    if not ratios:
        return float("nan")
    return float(np.mean(ratios))


def extract_workload_vector(workload: Workload) -> np.ndarray:
    """Converte um workload em vetor numérico na ordem de ``FEATURE_NAMES``."""
    cpu_req = workload.total_cpu_request_per_pod_millicores or 0.0
    mem_req_bytes = workload.total_memory_request_per_pod_bytes or 0.0
    mem_req_mib = mem_req_bytes / (1024**2)
    cpu_lim = _sum_container_limits_millicores(workload)
    mem_lim_mib = _sum_container_limits_bytes(workload) / (1024**2)
    replicas = float(workload.replicas_desired or 0)
    container_count = float(len(workload.containers))

    return np.array(
        [
            cpu_req,
            mem_req_mib,
            cpu_lim,
            mem_lim_mib,
            replicas,
            container_count,
            _safe_ratio(cpu_lim, cpu_req),
            _safe_ratio(mem_lim_mib * (1024**2), mem_req_bytes),
            _probe_ratio(workload, "readiness_probe"),
            _probe_ratio(workload, "liveness_probe"),
            1.0 if workload.node_selector else 0.0,
            1.0 if has_pod_anti_affinity(workload) else 0.0,
            _avg_usage_request_ratio(workload, resource="cpu"),
            _avg_usage_request_ratio(workload, resource="memory"),
        ],
        dtype=np.float64,
    )


def build_feature_matrix(workloads: tuple[Workload, ...]) -> FeatureMatrix:
    """Monta matriz (n_workloads × n_features) para o namespace."""
    if not workloads:
        return FeatureMatrix(workload_names=(), matrix=np.empty((0, len(FEATURE_NAMES))))

    names = tuple(w.name for w in workloads)
    rows = [extract_workload_vector(w) for w in workloads]
    return FeatureMatrix(
        workload_names=names,
        matrix=np.vstack(rows),
    )


def impute_nan_with_column_median(matrix: np.ndarray) -> np.ndarray:
    """Substitui NaN pela mediana da coluna (ex.: métricas ausentes).

    Colunas totalmente NaN permanecem como 0 para não quebrar escalonamento.
    """
    filled = matrix.copy()
    for col in range(filled.shape[1]):
        column = filled[:, col]
        mask = np.isnan(column)
        if not mask.any():
            continue
        if mask.all():
            filled[:, col] = 0.0
            continue
        median = float(np.nanmedian(column))
        column[mask] = median
        filled[:, col] = column
    return filled
