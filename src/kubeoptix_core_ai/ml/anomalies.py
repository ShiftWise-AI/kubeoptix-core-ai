"""Detecção de anomalias multivariadas com Isolation Forest.

Problema resolvido: encontrar workloads cujo *conjunto* de features se
comporta de forma atípica, mesmo quando nenhuma feature isolada ultrapassa
limites univariados (z-score / IQR).

Isolation Forest (scikit-learn):
- Executa 100% em CPU, sem rede;
- ``random_state`` garante reprodutibilidade;
- Não classifica automaticamente como defeito — apenas sinaliza investigação.

Justificativa da dependência: implementar Isolation Forest de forma
equivalente em stdlib não é prático; sklearn é leve e offline.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from kubeoptix_core_ai.ml.config import MLConfig
from kubeoptix_core_ai.ml.features import FeatureMatrix, impute_nan_with_column_median
from kubeoptix_core_ai.ml.findings_builder import MLFindingBuilder
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity


def analyze_anomalies(
    features: FeatureMatrix,
    namespace: str,
    config: MLConfig,
    builder: MLFindingBuilder,
) -> None:
    n = features.workload_count
    if n < config.min_workloads_anom:
        return

    imputed = impute_nan_with_column_median(features.matrix)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(imputed)

    contamination = config.isolation_contamination
    if contamination == "auto":
        # Heurística conservadora: no máximo ~20% ou 1 workload
        contamination = min(0.2, max(1 / n, 0.1))

    model = IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=config.random_seed,
        n_jobs=1,
    )
    predictions = model.fit_predict(scaled)
    scores = model.decision_function(scaled)

    for idx, pred in enumerate(predictions):
        if pred != -1:
            continue
        workload = features.workload_names[idx]
        score = float(scores[idx])
        builder.add(
            category="MLANOM",
            severity=Severity.LOW,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            workload=workload,
            evidence=(
                EvidenceItem(
                    description="Isolation Forest",
                    value=f"decision_function={score:.3f}, contamination={contamination}",
                ),
                EvidenceItem(
                    description="Features analisadas",
                    value=", ".join(features.feature_names),
                ),
            ),
            analysis=(
                f"O workload `{workload}` foi classificado como anomalia "
                "multivariada pelo Isolation Forest no perfil de recursos "
                f"e configuração do namespace (score {score:.3f})."
            ),
            impact=(
                "Combinação atípica de CPU/memória/réplicas/probes em relação "
                "aos demais workloads."
            ),
            recommendation=(
                "Validar manualmente se a configuração é intencional antes de "
                "alterar requests ou limits."
            ),
        )
