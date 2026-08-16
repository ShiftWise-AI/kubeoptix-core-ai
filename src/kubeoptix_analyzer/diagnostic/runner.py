"""Execução do diagnóstico de ingestão e normalização."""

from __future__ import annotations

from kubeoptix_analyzer.config import AnalyzerConfig
from kubeoptix_analyzer.diagnostic.aggregator import summarize_workloads, summarize_worknodes
from kubeoptix_analyzer.discovery.inventory import NamespaceFileInventory, scan_namespace_files
from kubeoptix_analyzer.errors import ConfigurationError
from kubeoptix_analyzer.loaders.workload_loader import WorkloadLoader
from kubeoptix_analyzer.loaders.worknode_loader import WorknodeLoader
from kubeoptix_analyzer.models.diagnostic import IngestionDiagnosticReport
from kubeoptix_analyzer.models.node import WorkNodeBundle
from kubeoptix_analyzer.models.workload import NamespaceWorkloadBundle


class DiagnosticRunner:
    """Valida ingestão e normalização sem gerar relatório final."""

    def __init__(self, config: AnalyzerConfig | None = None) -> None:
        self._config = config or AnalyzerConfig.from_env()
        self._workload_loader = WorkloadLoader(self._config)
        self._worknode_loader = WorknodeLoader(self._config)

    def run(self, namespace: str) -> IngestionDiagnosticReport:
        namespace_root = self._config.namespace_path(namespace)
        if not namespace_root.is_dir():
            raise ConfigurationError(
                f"Diretório do namespace não encontrado: {namespace_root}"
            )

        inventory = scan_namespace_files(namespace_root)
        bundle = self._workload_loader.load_namespace(namespace)
        node_bundle = self._worknode_loader.load()
        return self.build_report(namespace, bundle, node_bundle, inventory=inventory)

    def build_report(
        self,
        namespace: str,
        bundle: NamespaceWorkloadBundle,
        node_bundle: WorkNodeBundle,
        *,
        inventory: NamespaceFileInventory | None = None,
    ) -> IngestionDiagnosticReport:
        if inventory is None:
            inventory = scan_namespace_files(self._config.namespace_path(namespace))

        return IngestionDiagnosticReport(
            namespace=namespace,
            files_found_count=inventory.files_found_count,
            files_to_process_count=inventory.files_to_process_count,
            files_processed_count=len(bundle.processed_files),
            files_ignored_count=inventory.files_ignored_count,
            files_ignored=tuple(
                (ig.file_path, ig.reason) for ig in inventory.files_ignored
            ),
            parse_errors=bundle.parse_errors + node_bundle.parse_errors,
            processed_files=bundle.processed_files,
            workloads=summarize_workloads(bundle.workloads),
            worknodes=summarize_worknodes(node_bundle.nodes, node_bundle.parse_errors),
        )
