"""Orquestra diagnóstico, análise e preparação dos dados para o relatório."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from kubeoptix_analyzer.analysis.context import AnalysisContext
from kubeoptix_analyzer.analysis.engine import AnalysisEngine, NamespaceAnalysisResult
from kubeoptix_analyzer.config import AnalyzerConfig
from kubeoptix_analyzer.diagnostic.runner import DiagnosticRunner
from kubeoptix_analyzer.discovery.inventory import scan_namespace_files
from kubeoptix_analyzer.errors import ConfigurationError
from kubeoptix_analyzer.loaders.workload_loader import WorkloadLoader
from kubeoptix_analyzer.loaders.worknode_loader import WorknodeLoader
from kubeoptix_analyzer.ml.config import MLConfig
from kubeoptix_analyzer.models.diagnostic import IngestionDiagnosticReport
from kubeoptix_analyzer.models.finding import AnalysisReport


@dataclass(frozen=True)
class AssessmentBundle:
    """Dados consolidados para geração do relatório Markdown."""

    config: AnalyzerConfig
    analysis: AnalysisReport
    context: AnalysisContext
    diagnostic: IngestionDiagnosticReport
    generated_at: datetime


class AssessmentPipeline:
    """Executa diagnóstico + análise e entrega pacote para o gerador."""

    def __init__(
        self,
        config: AnalyzerConfig | None = None,
        ml_config: MLConfig | None = None,
    ) -> None:
        self._config = config or AnalyzerConfig.from_env()
        self._ml_config = ml_config or MLConfig.from_env()
        self._workload_loader = WorkloadLoader(self._config)
        self._worknode_loader = WorknodeLoader(self._config)
        self._engine = AnalysisEngine(self._config, ml_config=self._ml_config)
        self._diagnostic = DiagnosticRunner(self._config)

    def run(
        self,
        namespace: str,
        *,
        enable_ml: bool | None = None,
    ) -> AssessmentBundle:
        namespace_root = self._config.namespace_path(namespace)
        if not namespace_root.is_dir():
            raise ConfigurationError(
                f"Diretório do namespace não encontrado: {namespace_root}"
            )

        inventory = scan_namespace_files(namespace_root)
        bundle = self._workload_loader.load_namespace(namespace)
        node_bundle = self._worknode_loader.load()
        diagnostic = self._diagnostic.build_report(
            namespace,
            bundle,
            node_bundle,
            inventory=inventory,
        )
        result: NamespaceAnalysisResult = self._engine.analyze_bundle(
            bundle,
            node_bundle.nodes,
            enable_ml=enable_ml,
        )
        return AssessmentBundle(
            config=self._config,
            analysis=result.report,
            context=result.context,
            diagnostic=diagnostic,
            generated_at=datetime.now(timezone.utc),
        )
