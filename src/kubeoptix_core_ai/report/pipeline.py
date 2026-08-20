"""Orquestra diagnóstico, análise e preparação dos dados para o relatório."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.engine import AnalysisEngine, NamespaceAnalysisResult
from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.diagnostic.runner import DiagnosticRunner
from kubeoptix_core_ai.discovery.inventory import NamespaceFileInventory, scan_namespace_files
from kubeoptix_core_ai.errors import ConfigurationError
from kubeoptix_core_ai.loaders.workload_loader import WorkloadLoader
from kubeoptix_core_ai.loaders.worknode_loader import WorknodeLoader
from kubeoptix_core_ai.ml.config import MLConfig
from kubeoptix_core_ai.models.diagnostic import IngestionDiagnosticReport
from kubeoptix_core_ai.models.finding import AnalysisReport


class AnalysisProgress(Protocol):
    """Notificações de etapa usadas pelo pipeline (implementado pela API)."""

    def yamls_identified(self, count: int) -> None: ...

    def yaml_read_started(self) -> None: ...

    def yaml_file_processed(self, processed: int, total: int) -> None: ...

    def yaml_read_finished(self) -> None: ...

    def analysis_step(self, step: int, step_count: int, label: str) -> None: ...

    def analysis_finished(self) -> None: ...


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
        inventory: NamespaceFileInventory | None = None,
        progress: AnalysisProgress | None = None,
    ) -> AssessmentBundle:
        namespace_root = self._config.namespace_path(namespace)
        if not namespace_root.is_dir():
            raise ConfigurationError(
                f"Diretório do namespace não encontrado: {namespace_root}"
            )

        if inventory is None:
            inventory = scan_namespace_files(namespace_root)
        if progress is not None:
            progress.yamls_identified(inventory.files_to_process_count)
            progress.yaml_read_started()

        on_file = progress.yaml_file_processed if progress is not None else None
        bundle = self._workload_loader.load_namespace(
            namespace,
            on_file_processed=on_file,
        )
        node_bundle = self._worknode_loader.load()
        if progress is not None:
            progress.yaml_read_finished()

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
            on_analysis_step=(
                progress.analysis_step if progress is not None else None
            ),
        )
        if progress is not None:
            progress.analysis_finished()
        return AssessmentBundle(
            config=self._config,
            analysis=result.report,
            context=result.context,
            diagnostic=diagnostic,
            generated_at=datetime.now(timezone.utc),
        )
