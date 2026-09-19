"""Agrupamento de workloads por perfil de recursos (K-Means).

Problema resolvido: descobrir grupos naturais de workloads com perfis
semelhantes (ex.: frontends leves vs backends pesados) para orientar
comparações de right-sizing dentro do mesmo grupo.

K-Means (scikit-learn):
- inicialização determinística para manter resposta estável entre execuções;
- k escolhido automaticamente entre 2 e min(4, n-1);
- sem depender de RNG aleatório para definir centroides iniciais.

Não substitui labels ou nomes de aplicação — apenas agrupa por números.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from kubeoptix_core_ai.ml.config import MLConfig
from kubeoptix_core_ai.ml.features import FeatureMatrix, impute_nan_with_column_median
from kubeoptix_core_ai.ml.findings_builder import MLFindingBuilder
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity


def _choose_k(workload_count: int) -> int | None:
    if workload_count < 3:
        return None
    return min(4, max(2, workload_count // 2))


def _deterministic_kmeans_init(data: np.ndarray, n_clusters: int) -> np.ndarray:
    """Seleciona centroides iniciais fixos por ordenação determinística.

    O ``KMeans`` padrão usa ``k-means++`` e pode convergir para diferentes
    partições equivalentes para o mesmo conjunto de dados, dependendo do estado
    aleatório do processo. Para manter a análise estável, partimos de centroides
    extraídos em posições espaçadas da ordenação canônica das features.
    """
    if len(data) < n_clusters:
        raise ValueError("Dados insuficientes para inicializar KMeans determinístico")

    order = np.lexsort(tuple(data[:, idx] for idx in range(data.shape[1] - 1, -1, -1)))
    indices = np.linspace(0, len(order) - 1, n_clusters, dtype=int)
    return data[order[indices]]


def analyze_clustering(
    features: FeatureMatrix,
    namespace: str,
    config: MLConfig,
    builder: MLFindingBuilder,
) -> None:
    n = features.workload_count
    if n < config.min_workloads_cluster:
        return

    k = _choose_k(n)
    if k is None or k >= n:
        return

    imputed = impute_nan_with_column_median(features.matrix)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(imputed)

    model = KMeans(
        n_clusters=k,
        init=_deterministic_kmeans_init(scaled, k),
        n_init=1,
        random_state=config.random_seed,
        algorithm="lloyd",
    )
    labels = model.fit_predict(scaled)

    clusters: dict[int, list[str]] = {}
    for workload, label in zip(features.workload_names, labels, strict=True):
        clusters.setdefault(int(label), []).append(workload)

    # Rótulos do K-Means são arbitrários; ordenação canônica para reprodutibilidade.
    canonical_groups = [
        ", ".join(sorted(names))
        for _, names in sorted(clusters.items(), key=lambda item: min(item[1]))
    ]
    cluster_summary = "; ".join(f"[{group}]" for group in canonical_groups)
    builder.add(
        category="MLCLUST",
        severity=Severity.INFO,
        confidence=Confidence.MEDIUM,
        namespace=namespace,
        evidence=(
            EvidenceItem(
                description="K-Means",
                value=f"k={k}, seed={config.random_seed}",
            ),
            EvidenceItem(
                description="Composição dos grupos",
                value=cluster_summary,
            ),
        ),
        analysis=(
            f"K-Means (k={k}) agrupou os {n} workloads do namespace em "
            f"perfis numéricos: {cluster_summary}."
        ),
        impact=(
            "Facilita comparar right-sizing entre workloads do mesmo grupo "
            "em vez de tratar o namespace como homogêneo."
        ),
        recommendation=(
            "Revisar discrepâncias de recursos entre workloads dentro do "
            "mesmo grupo identificado."
        ),
    )

    # Workload isolado em cluster singleton (possível outlier de papel)
    for cid, names in clusters.items():
        if len(names) != 1:
            continue
        workload = names[0]
        builder.add(
            category="MLCLUST",
            severity=Severity.INFO,
            confidence=Confidence.LOW,
            namespace=namespace,
            workload=workload,
            evidence=(
                EvidenceItem(
                    description="Cluster singleton",
                    value=f"membros: {', '.join(sorted(names))}",
                ),
            ),
            analysis=(
                f"O workload `{workload}` forma um grupo isolado (singleton) "
                f"no clustering k={k} — perfil numérico distinto dos demais."
            ),
            recommendation=(
                "Confirmar se o workload exerce função única no namespace "
                "ou se há oportunidade de alinhar recursos a um grupo existente."
            ),
        )
