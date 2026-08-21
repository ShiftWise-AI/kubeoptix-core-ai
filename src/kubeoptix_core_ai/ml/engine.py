"""Orquestração da camada estatística / ML local."""

from __future__ import annotations

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.ml.anomalies import analyze_anomalies
from kubeoptix_core_ai.ml.clustering import analyze_clustering
from kubeoptix_core_ai.ml.comparison import analyze_comparison
from kubeoptix_core_ai.ml.config import MLConfig
from kubeoptix_core_ai.ml.features import build_feature_matrix
from kubeoptix_core_ai.ml.findings_builder import MLFindingBuilder
from kubeoptix_core_ai.ml.fleet import FleetBaseline, analyze_fleet, fleet_is_usable
from kubeoptix_core_ai.ml.similarity import analyze_similarity
from kubeoptix_core_ai.ml.statistics import analyze_statistics
from kubeoptix_core_ai.models.finding import Finding


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

    def analyze(
        self,
        ctx: AnalysisContext,
        fleet: FleetBaseline | None = None,
    ) -> tuple[tuple[Finding, ...], tuple[str, ...]]:
        """Retorna (findings, limitações adicionais da camada ML)."""
        limitations: list[str] = []
        builder = MLFindingBuilder()

        workloads = ctx.workloads
        features = build_feature_matrix(workloads) if workloads else None

        if not ctx.has_runtime_metrics:
            limitations.append(
                "Features de usage/request derivadas de PodMetrics ausentes; "
                "imputação por mediana da coluna ou exclusão implícita."
            )

        use_fleet = fleet_is_usable(fleet, ctx.namespace, self._config)
        if use_fleet and fleet is not None and features is not None:
            analyze_fleet(features, ctx.namespace, fleet, self._config, builder)
            limitations.append(
                f"Baseline de frota: {fleet.workload_count} workload(s) em "
                f"{fleet.namespace_count} namespace(s) do dump "
                f"(percentis e Isolation Forest excluem `{ctx.namespace}`)."
            )
        elif fleet is not None and not use_fleet:
            limitations.append(
                "Baseline de frota omitida: namespaces/workloads insuficientes "
                "fora do namespace analisado."
            )

        if len(workloads) < 2:
            limitations.append(
                "Menos de 2 workloads no namespace: similaridade e clustering "
                "intra-namespace omitidos."
            )
            if not builder.findings:
                return builder.findings, tuple(limitations)
        elif features is not None:
            analyze_statistics(features, ctx.namespace, self._config, builder)
            analyze_comparison(features, ctx.namespace, self._config, builder)
            if not use_fleet:
                analyze_anomalies(features, ctx.namespace, self._config, builder)
            analyze_clustering(features, ctx.namespace, self._config, builder)
            analyze_similarity(features, ctx.namespace, self._config, builder)

        if not builder.findings:
            limitations.append(
                "Nenhum sinal estatístico / ML acima dos limiares configurados."
            )

        return builder.findings, tuple(limitations)
