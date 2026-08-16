"""Comparação multivariada de workloads no namespace.

Problema resolvido: resumir o quanto cada workload se afasta do perfil
típico do namespace em múltiplas dimensões (recursos, réplicas, probes).

Usa distância euclidiana no espaço padronizado (z-score por coluna) —
equivalente a comparar perfis numéricos sem embeddings textuais.
"""

from __future__ import annotations

import numpy as np

from kubeoptix_analyzer.ml.config import MLConfig
from kubeoptix_analyzer.ml.features import FeatureMatrix, impute_nan_with_column_median
from kubeoptix_analyzer.ml.findings_builder import MLFindingBuilder
from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Severity


def _standardize(matrix: np.ndarray) -> np.ndarray:
    imputed = impute_nan_with_column_median(matrix)
    mean = imputed.mean(axis=0)
    std = imputed.std(axis=0)
    std[std == 0] = 1.0
    return (imputed - mean) / std


def analyze_comparison(
    features: FeatureMatrix,
    namespace: str,
    config: MLConfig,
    builder: MLFindingBuilder,
) -> None:
    if features.workload_count < config.min_workloads_stat:
        return

    scaled = _standardize(features.matrix)
    centroid = scaled.mean(axis=0)
    distances = np.linalg.norm(scaled - centroid, axis=1)
    if distances.max() == distances.min():
        return

    outlier_idx = int(distances.argmax())
    workload = features.workload_names[outlier_idx]
    dist = float(distances[outlier_idx])
    mean_dist = float(distances.mean())

    if dist < mean_dist * 1.5:
        return

    builder.add(
        category="MLCOMP",
        severity=Severity.INFO,
        confidence=Confidence.MEDIUM,
        namespace=namespace,
        workload=workload,
        evidence=(
            EvidenceItem(
                description="Distância euclidiana ao centroide (features padronizadas)",
                value=f"{dist:.2f} (média do namespace: {mean_dist:.2f})",
            ),
        ),
        analysis=(
            f"O workload `{workload}` é o mais distante do perfil médio do "
            f"namespace no espaço de features estruturadas (distância "
            f"{dist:.2f} vs média {mean_dist:.2f})."
        ),
        impact=(
            "Pode representar papel operacional diferente (ex.: batch vs API) "
            "ou configuração inconsistente com pares do namespace."
        ),
        recommendation=(
            "Revisar se o perfil de recursos e réplicas está alinhado à "
            "função do workload."
        ),
    )

    if features.workload_count >= 2:
        max_pair_dist = -1.0
        pair: tuple[int, int] | None = None
        for i in range(len(distances)):
            for j in range(i + 1, len(distances)):
                d = float(np.linalg.norm(scaled[i] - scaled[j]))
                if d > max_pair_dist:
                    max_pair_dist = d
                    pair = (i, j)
        if pair and max_pair_dist > 0:
            w_a = features.workload_names[pair[0]]
            w_b = features.workload_names[pair[1]]
            builder.add(
                category="MLCOMP",
                severity=Severity.INFO,
                confidence=Confidence.MEDIUM,
                namespace=namespace,
                evidence=(
                    EvidenceItem(
                        description="Par de workloads",
                        value=f"{w_a} ↔ {w_b}",
                    ),
                    EvidenceItem(
                        description="Distância euclidiana",
                        value=f"{max_pair_dist:.2f}",
                    ),
                ),
                analysis=(
                    f"Os workloads `{w_a}` e `{w_b}` são o par mais divergente "
                    f"do namespace (distância {max_pair_dist:.2f} no espaço "
                    "de features padronizadas)."
                ),
                recommendation=(
                    "Útil para priorizar revisões de right-sizing entre "
                    "componentes de arquiteturas distintas no mesmo namespace."
                ),
            )
