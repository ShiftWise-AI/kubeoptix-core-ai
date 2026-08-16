"""Orquestração da camada estatística / ML local."""

from __future__ import annotations

from kubeoptix_analyzer.analysis.context import AnalysisContext
from kubeoptix_analyzer.ml.anomalies import analyze_anomalies
from kubeoptix_analyzer.ml.clustering import analyze_clustering
from kubeoptix_analyzer.ml.comparison import analyze_comparison
from kubeoptix_analyzer.ml.config import MLConfig
from kubeoptix_analyzer.ml.features import build_feature_matrix
from kubeoptix_analyzer.ml.findings_builder import MLFindingBuilder
from kubeoptix_analyzer.ml.similarity import analyze_similarity
from kubeoptix_analyzer.ml.statistics import analyze_statistics
from kubeoptix_analyzer.models.finding import Finding


class MLEngine:
    """Executa análise estatística e ML local após a camada determinística.

    Ordem de execução (prioridade da metodologia):
    1. Estatística (z-score, IQR)
    2. Comparação multivariada
    3. Anomalias (Isolation Forest)
    4. Clustering (K-Means)
    5. Similaridade (cosseno)

    Embeddings textuais não são utilizados: features estruturadas são
    suficientes para os objetivos de right-sizing e comparação operacional.
    """

    def __init__(self, config: MLConfig | None = None) -> None:
        self._config = config or MLConfig.from_env()

    @property
    def config(self) -> MLConfig:
        return self._config

    def analyze(self, ctx: AnalysisContext) -> tuple[tuple[Finding, ...], tuple[str, ...]]:
        """Retorna (findings, limitações adicionais da camada ML)."""
        limitations: list[str] = []
        builder = MLFindingBuilder()

        workloads = ctx.workloads
        if len(workloads) < 2:
            limitations.append(
                "Menos de 2 workloads no namespace: análise estatística "
                "e similaridade omitidas."
            )
            return builder.findings, tuple(limitations)

        features = build_feature_matrix(workloads)

        if not ctx.has_runtime_metrics:
            limitations.append(
                "Features de usage/request derivadas de PodMetrics ausentes; "
                "imputação por mediana da coluna ou exclusão implícita."
            )

        analyze_statistics(features, ctx.namespace, self._config, builder)
        analyze_comparison(features, ctx.namespace, self._config, builder)
        analyze_anomalies(features, ctx.namespace, self._config, builder)
        analyze_clustering(features, ctx.namespace, self._config, builder)
        analyze_similarity(features, ctx.namespace, self._config, builder)

        if not builder.findings:
            limitations.append(
                "Nenhum sinal estatístico / ML acima dos limiares configurados."
            )

        return builder.findings, tuple(limitations)
