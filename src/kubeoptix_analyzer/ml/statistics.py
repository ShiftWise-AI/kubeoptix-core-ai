"""Análise estatística descritiva e detecção de outliers (z-score e IQR).

Problema resolvido: identificar workloads que se destacam *em relação aos
demais do mesmo namespace*, sem substituir regras absolutas (ex.: request
ausente continua sendo tratado pela camada determinística).

Técnicas:
- z-score robusto (mediana/MAD): resistente a outliers extremos que distorcem
  média e desvio-padrão clássicos; adequado para comparar workloads no namespace.
- IQR (Tukey): robusto a assimetria; detecta valores fora de
  [Q1 - k·IQR, Q3 + k·IQR].

Implementação com ``statistics`` (stdlib) — sem dependência extra.
"""

from __future__ import annotations

import math
import statistics

from kubeoptix_analyzer.analysis.helpers import format_cpu_millicores, format_memory_bytes
from kubeoptix_analyzer.ml.config import MLConfig
from kubeoptix_analyzer.ml.features import FEATURE_DESCRIPTIONS, FeatureMatrix
from kubeoptix_analyzer.ml.findings_builder import MLFindingBuilder
from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Severity

# Features prioritárias para outliers univariados (evita ruído em flags 0/1)
_STAT_FEATURES = (
    "cpu_request_m",
    "mem_request_mib",
    "replicas",
    "cpu_usage_request_ratio",
    "mem_usage_request_ratio",
)


def _format_feature_value(feature: str, value: float) -> str:
    if not math.isfinite(value):
        return "N/A"
    if feature == "cpu_request_m":
        return format_cpu_millicores(value)
    if feature == "mem_request_mib":
        return format_memory_bytes(value * (1024**2))
    if feature.endswith("_ratio"):
        return f"{value:.2f}"
    if feature == "replicas":
        return str(int(round(value)))
    return f"{value:.2f}"


def _finite_values(column: list[float]) -> list[float]:
    return [v for v in column if math.isfinite(v)]


def _classic_zscore_outliers(
    values: list[float],
    threshold: float,
) -> list[tuple[int, float, float]]:
    """z-score clássico (média/desvio); fallback quando MAD=0."""
    finite = _finite_values(values)
    if len(finite) < 2:
        return []
    stdev = statistics.pstdev(finite)
    if stdev == 0:
        return []
    mean = statistics.mean(finite)
    results: list[tuple[int, float, float]] = []
    for idx, value in enumerate(values):
        if not math.isfinite(value):
            continue
        z = (value - mean) / stdev
        if abs(z) + 1e-12 >= threshold:
            results.append((idx, z, value))
    return results


def _robust_zscore_outliers(
    values: list[float],
    threshold: float,
) -> list[tuple[int, float, float]]:
    """z-score robusto via mediana e MAD (modified z-score)."""
    finite = _finite_values(values)
    if len(finite) < 3:
        return _classic_zscore_outliers(values, threshold)
    median = statistics.median(finite)
    mad = statistics.median(abs(v - median) for v in finite)
    if mad == 0:
        return _classic_zscore_outliers(values, threshold)
    results: list[tuple[int, float, float]] = []
    for idx, value in enumerate(values):
        if not math.isfinite(value):
            continue
        robust_z = 0.6745 * abs(value - median) / mad
        if robust_z + 1e-12 >= threshold:
            results.append((idx, robust_z, value))
    return results


def _iqr_outliers(
    values: list[float],
    multiplier: float,
) -> list[tuple[int, float, str]]:
    """Retorna (índice, valor, lado) para outliers IQR."""
    finite = _finite_values(values)
    if len(finite) < 4:
        return []
    sorted_vals = sorted(finite)
    q1 = statistics.quantiles(sorted_vals, n=4)[0]
    q3 = statistics.quantiles(sorted_vals, n=4)[2]
    iqr = q3 - q1
    if iqr == 0:
        return []
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    results: list[tuple[int, float, str]] = []
    for idx, value in enumerate(values):
        if not math.isfinite(value):
            continue
        if value < lower:
            results.append((idx, value, "abaixo"))
        elif value > upper:
            results.append((idx, value, "acima"))
    return results


def analyze_statistics(
    features: FeatureMatrix,
    namespace: str,
    config: MLConfig,
    builder: MLFindingBuilder,
) -> None:
    if features.workload_count < config.min_workloads_stat:
        return

    name_to_idx = {name: i for i, name in enumerate(features.feature_names)}

    for feature in _STAT_FEATURES:
        if feature not in name_to_idx:
            continue
        col_idx = name_to_idx[feature]
        column = features.matrix[:, col_idx].tolist()
        finite = _finite_values(column)
        if len(finite) < config.min_workloads_stat:
            continue
        if max(finite) == min(finite):
            continue

        desc = FEATURE_DESCRIPTIONS[feature]
        formatted_values = {i: _format_feature_value(feature, v) for i, v in enumerate(column)}

        for idx, z, value in _robust_zscore_outliers(column, config.zscore_threshold):
            workload = features.workload_names[idx]
            builder.add(
                category="MLSTAT",
                severity=Severity.INFO,
                confidence=Confidence.MEDIUM,
                namespace=namespace,
                workload=workload,
                evidence=(
                    EvidenceItem(
                        description=f"Feature: {feature}",
                        value=f"z-score={z:.2f}, valor={formatted_values[idx]}",
                    ),
                    EvidenceItem(
                        description="Referência",
                        value=desc,
                    ),
                ),
                analysis=(
                    f"O workload `{workload}` apresenta `{feature}` "
                    f"({formatted_values[idx]}) com z-score robusto (mediana/MAD) "
                    f"de {z:.1f} no namespace (limiar {config.zscore_threshold})."
                ),
                impact=(
                    "Pode indicar perfil de recursos atípico em relação aos "
                    "demais workloads do namespace."
                ),
                recommendation=(
                    "Comparar com workloads semelhantes e validar se o "
                    "dimensionamento é intencional."
                ),
            )

        for idx, value, side in _iqr_outliers(column, config.iqr_multiplier):
            workload = features.workload_names[idx]
            builder.add(
                category="MLSTAT",
                severity=Severity.INFO,
                confidence=Confidence.MEDIUM,
                namespace=namespace,
                workload=workload,
                evidence=(
                    EvidenceItem(
                        description=f"Feature: {feature}",
                        value=f"valor={formatted_values[idx]}, lado={side}",
                    ),
                ),
                analysis=(
                    f"Pelos limites IQR (k={config.iqr_multiplier}), o workload "
                    f"`{workload}` está {side} do intervalo esperado para "
                    f"`{feature}` ({formatted_values[idx]})."
                ),
                recommendation="Investigar se o valor é outlier legítimo ou erro de configuração.",
            )
