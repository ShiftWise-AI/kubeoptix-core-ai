"""Baseline estatística de frota (todos os namespaces do dump).

Compara o namespace analisado a percentis e Isolation Forest treinados
no conjunto de workloads corporativos — não só nos pares do mesmo NS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from kubeoptix_core_ai.ml.config import MLConfig
from kubeoptix_core_ai.ml.features import (
    FEATURE_DESCRIPTIONS,
    FEATURE_NAMES,
    FeatureMatrix,
    extract_workload_vector,
    impute_nan_with_column_median,
)
from kubeoptix_core_ai.ml.findings_builder import MLFindingBuilder
from kubeoptix_core_ai.ml.statistics import _format_feature_value
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity
from kubeoptix_core_ai.models.workload import Workload

_PERCENTILE_FEATURES = (
    "cpu_request_m",
    "mem_request_mib",
    "cpu_usage_request_ratio",
    "mem_usage_request_ratio",
    "replicas",
)


@dataclass(frozen=True)
class FleetBaseline:
    """Matriz de features de todos os workloads carregados no dump."""

    workload_keys: tuple[tuple[str, str], ...]  # (namespace, name)
    matrix: np.ndarray
    feature_names: tuple[str, ...] = FEATURE_NAMES

    @property
    def workload_count(self) -> int:
        return len(self.workload_keys)

    @property
    def namespace_count(self) -> int:
        return len({ns for ns, _ in self.workload_keys})

    def matrix_excluding(self, namespace: str) -> np.ndarray:
        mask = np.array([ns != namespace for ns, _ in self.workload_keys])
        if not mask.any():
            return np.empty((0, self.matrix.shape[1]))
        return self.matrix[mask]


def build_fleet_baseline(workloads: tuple[Workload, ...]) -> FleetBaseline | None:
    if not workloads:
        return None
    keys = tuple((w.namespace, w.name) for w in workloads)
    rows = [extract_workload_vector(w) for w in workloads]
    return FleetBaseline(
        workload_keys=keys,
        matrix=np.vstack(rows),
    )


def fleet_is_usable(
    fleet: FleetBaseline | None,
    namespace: str,
    config: MLConfig,
) -> bool:
    if fleet is None:
        return False
    other = fleet.matrix_excluding(namespace)
    other_ns = {ns for ns, _ in fleet.workload_keys if ns != namespace}
    return (
        len(other_ns) >= config.min_fleet_namespaces - 1
        and other.shape[0] >= config.min_fleet_workloads
    )


def _percentile_map(matrix: np.ndarray) -> dict[str, tuple[float, float, float]]:
    result: dict[str, tuple[float, float, float]] = {}
    for idx, name in enumerate(FEATURE_NAMES):
        column = matrix[:, idx].astype(float)
        finite = column[np.isfinite(column)]
        if finite.size < 3:
            continue
        p10, p50, p90 = np.nanpercentile(finite, [10, 50, 90])
        result[name] = (float(p10), float(p50), float(p90))
    return result


def analyze_fleet(
    features: FeatureMatrix,
    namespace: str,
    fleet: FleetBaseline,
    config: MLConfig,
    builder: MLFindingBuilder,
) -> None:
    """Percentis P10/P50/P90 e Isolation Forest contra a frota (exceto o NS)."""
    other = fleet.matrix_excluding(namespace)
    if other.shape[0] < config.min_fleet_workloads:
        return

    percentiles = _percentile_map(other)
    name_to_idx = {name: i for i, name in enumerate(features.feature_names)}
    fleet_ns = fleet.namespace_count
    fleet_n = other.shape[0]

    for feature in _PERCENTILE_FEATURES:
        if feature not in percentiles or feature not in name_to_idx:
            continue
        p10, p50, p90 = percentiles[feature]
        col = name_to_idx[feature]
        desc = FEATURE_DESCRIPTIONS.get(feature, feature)
        for idx, value in enumerate(features.matrix[:, col].tolist()):
            if not np.isfinite(value):
                continue
            side: str | None = None
            ref = p50
            if feature.endswith("_ratio") and "usage" in feature:
                if value > p90 and p90 > 0:
                    side = "acima do P90 da frota"
                    ref = p90
                elif value < p10:
                    side = "abaixo do P10 da frota"
                    ref = p10
            elif value > p90 * 1.25 and p90 > 0:
                side = "acima do P90 da frota"
                ref = p90
            elif value < p10 * 0.5 and p10 > 0:
                side = "abaixo do P10 da frota"
                ref = p10
            if side is None:
                continue
            workload = features.workload_names[idx]
            builder.add(
                category="MLFLEET",
                severity=Severity.INFO,
                confidence=Confidence.MEDIUM,
                namespace=namespace,
                workload=workload,
                evidence=(
                    EvidenceItem(
                        description=f"Feature: {feature}",
                        value=(
                            f"valor={_format_feature_value(feature, value)}, "
                            f"P10={_format_feature_value(feature, p10)}, "
                            f"P50={_format_feature_value(feature, p50)}, "
                            f"P90={_format_feature_value(feature, p90)}"
                        ),
                    ),
                    EvidenceItem(
                        description="Baseline",
                        value=f"{fleet_n} workloads em {fleet_ns} namespaces; {desc}",
                    ),
                ),
                analysis=(
                    f"O workload `{workload}` tem `{feature}` "
                    f"({_format_feature_value(feature, value)}) {side} "
                    f"(P50={_format_feature_value(feature, ref)})."
                ),
                impact=(
                    "Perfil diferente da mediana corporativa; pode ser intencional "
                    "ou indicar right-sizing."
                ),
                recommendation=(
                    "Comparar com workloads semelhantes da frota antes de alterar "
                    "requests/limits."
                ),
                limitation=(
                    f"Percentis calculados em {fleet_n} workloads de outros "
                    "namespaces do mesmo dump. Outlier estatístico ≠ defeito."
                ),
            )

    _analyze_fleet_anomalies(features, namespace, other, fleet_n, fleet_ns, config, builder)


def _analyze_fleet_anomalies(
    features: FeatureMatrix,
    namespace: str,
    fleet_matrix: np.ndarray,
    fleet_n: int,
    fleet_ns: int,
    config: MLConfig,
    builder: MLFindingBuilder,
) -> None:
    if features.workload_count < 1 or fleet_matrix.shape[0] < config.min_workloads_anom:
        return

    fleet_imputed = impute_nan_with_column_median(fleet_matrix)
    ns_imputed = impute_nan_with_column_median(features.matrix)
    scaler = StandardScaler()
    fleet_scaled = scaler.fit_transform(fleet_imputed)
    ns_scaled = scaler.transform(ns_imputed)

    model = IsolationForest(
        n_estimators=100,
        contamination="auto",
        random_state=config.random_seed,
        n_jobs=1,
    )
    model.fit(fleet_scaled)
    fleet_scores = model.decision_function(fleet_scaled)
    ns_scores = model.decision_function(ns_scaled)
    threshold = float(np.percentile(fleet_scores, 10))

    for idx, score in enumerate(ns_scores):
        if float(score) >= threshold:
            continue
        workload = features.workload_names[idx]
        builder.add(
            category="MLANOM",
            severity=Severity.LOW,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            workload=workload,
            evidence=(
                EvidenceItem(
                    description="Isolation Forest (frota)",
                    value=(
                        f"decision_function={float(score):.3f}, "
                        f"P10 frota={threshold:.3f}"
                    ),
                ),
                EvidenceItem(
                    description="Baseline",
                    value=f"{fleet_n} workloads / {fleet_ns} namespaces",
                ),
            ),
            analysis=(
                f"O workload `{workload}` ficou abaixo do P10 dos scores do "
                "Isolation Forest treinado na frota corporativa "
                f"(score {float(score):.3f})."
            ),
            impact=(
                "Combinação atípica de recursos/configuração em relação à frota, "
                "não apenas aos pares do namespace."
            ),
            recommendation=(
                "Validar se o perfil é intencional (batch, cache, DB) antes de "
                "alterar requests."
            ),
            limitation=(
                "Modelo treinado nos demais namespaces do dump. "
                "Outlier estatístico não implica defeito operacional."
            ),
        )
