"""Similaridade entre workloads via distância de cosseno.

Problema resolvido: encontrar pares de workloads com perfis de recursos
*numericamente* parecidos para benchmarking interno (ex.: dois backends
com requests quase iguais).

Implementação com numpy (já dependência transitiva de scikit-learn).
Não usamos embeddings textuais nem TF-IDF sobre YAML: a similaridade
semântica de nomes não prova equivalência operacional (conforme metodologia).

Similaridade alta não implica que os workloads devam ter a mesma configuração —
apenas que, nos números observados, se parecem.
"""

from __future__ import annotations

import numpy as np
from sklearn.preprocessing import StandardScaler

from kubeoptix_analyzer.ml.config import MLConfig
from kubeoptix_analyzer.ml.features import FeatureMatrix, impute_nan_with_column_median
from kubeoptix_analyzer.ml.findings_builder import MLFindingBuilder
from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Severity


def _cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = vectors / norms
    return normalized @ normalized.T


def analyze_similarity(
    features: FeatureMatrix,
    namespace: str,
    config: MLConfig,
    builder: MLFindingBuilder,
) -> None:
    n = features.workload_count
    if n < config.min_workloads_similarity:
        return

    imputed = impute_nan_with_column_median(features.matrix)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(imputed)
    sim = _cosine_similarity_matrix(scaled)

    reported: set[tuple[str, str]] = set()
    for i in range(n):
        for j in range(i + 1, n):
            similarity = float(sim[i, j])
            if similarity < config.similarity_threshold:
                continue
            w_a = features.workload_names[i]
            w_b = features.workload_names[j]
            key = tuple(sorted((w_a, w_b)))
            if key in reported:
                continue
            reported.add(key)

            builder.add(
                category="MLSIM",
                severity=Severity.INFO,
                confidence=Confidence.MEDIUM,
                namespace=namespace,
                evidence=(
                    EvidenceItem(
                        description="Par de workloads",
                        value=f"{w_a} ↔ {w_b}",
                    ),
                    EvidenceItem(
                        description="Similaridade de cosseno",
                        value=f"{similarity:.3f} (limiar {config.similarity_threshold})",
                    ),
                ),
                analysis=(
                    f"Os workloads `{w_a}` e `{w_b}` apresentam perfil de "
                    f"features estruturadas muito similar (cosseno "
                    f"{similarity:.1%}) no namespace."
                ),
                impact=(
                    "Candidatos naturais para comparação de utilização real "
                    "e harmonização de requests/limits."
                ),
                recommendation=(
                    "Se um dos workloads apresentar métricas de runtime "
                    "divergentes, investigar diferenças de código, tráfego "
                    "ou configuração não capturada nas features numéricas."
                ),
            )
