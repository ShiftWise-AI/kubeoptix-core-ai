"""Orquestração da análise determinística."""

from __future__ import annotations

from dataclasses import dataclass

from kubeoptix_analyzer.analysis.context import AnalysisContext
from kubeoptix_analyzer.analysis.cpu import analyze_cpu
from kubeoptix_analyzer.analysis.inventory import analyze_inventory
from kubeoptix_analyzer.analysis.findings_builder import FindingBuilder
from kubeoptix_analyzer.analysis.memory import analyze_memory
from kubeoptix_analyzer.analysis.probes import analyze_probes
from kubeoptix_analyzer.analysis.qos import analyze_qos
from kubeoptix_analyzer.analysis.replicas import analyze_replicas
from kubeoptix_analyzer.analysis.resources import analyze_resources
from kubeoptix_analyzer.analysis.scheduling import analyze_scheduling
from kubeoptix_analyzer.analysis.storage import analyze_storage
from kubeoptix_analyzer.analysis.workload_node import analyze_workload_node
from kubeoptix_analyzer.config import AnalyzerConfig
from kubeoptix_analyzer.loaders.workload_loader import WorkloadLoader
from kubeoptix_analyzer.loaders.worknode_loader import WorknodeLoader
from kubeoptix_analyzer.ml.config import MLConfig
from kubeoptix_analyzer.ml.engine import MLEngine
from kubeoptix_analyzer.models.finding import AnalysisReport, Finding, Severity
from kubeoptix_analyzer.models.node import WorkNode
from kubeoptix_analyzer.models.workload import NamespaceWorkloadBundle

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def _sort_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    return tuple(
        sorted(
            findings,
            key=lambda f: (_SEVERITY_ORDER[f.severity], f.category, f.id),
        )
    )


@dataclass(frozen=True)
class NamespaceAnalysisResult:
    """Resultado completo da análise, incluindo contexto para relatório."""

    report: AnalysisReport
    context: AnalysisContext


class AnalysisEngine:
    """Executa análise determinística e, opcionalmente, ML local."""

    def __init__(
        self,
        config: AnalyzerConfig | None = None,
        ml_config: MLConfig | None = None,
    ) -> None:
        self._config = config or AnalyzerConfig.from_env()
        self._ml_config = ml_config or MLConfig.from_env()
        self._workload_loader = WorkloadLoader(self._config)
        self._worknode_loader = WorknodeLoader(self._config)
        self._ml_engine = MLEngine(self._ml_config)

    def analyze_namespace(
        self,
        namespace: str,
        *,
        enable_ml: bool | None = None,
    ) -> AnalysisReport:
        return self.analyze_namespace_full(namespace, enable_ml=enable_ml).report

    def analyze_namespace_full(
        self,
        namespace: str,
        *,
        enable_ml: bool | None = None,
    ) -> NamespaceAnalysisResult:
        bundle = self._workload_loader.load_namespace(namespace)
        node_bundle = self._worknode_loader.load()
        return self.analyze_bundle(
            bundle,
            node_bundle.nodes,
            enable_ml=enable_ml,
        )

    def analyze_bundle(
        self,
        bundle: NamespaceWorkloadBundle,
        nodes: tuple[WorkNode, ...],
        *,
        enable_ml: bool | None = None,
    ) -> NamespaceAnalysisResult:
        ctx = AnalysisContext(bundle=bundle, nodes=nodes)
        builder = FindingBuilder()

        analyze_cpu(ctx, builder)
        analyze_memory(ctx, builder)
        analyze_resources(ctx, builder)
        analyze_qos(ctx, builder)
        analyze_replicas(ctx, builder)
        analyze_probes(ctx, builder)
        analyze_scheduling(ctx, builder)
        analyze_storage(ctx, builder)
        analyze_inventory(ctx, builder)
        analyze_workload_node(ctx, builder)

        ml_enabled = enable_ml if enable_ml is not None else self._ml_config.enabled
        if ml_enabled:
            ml_findings, ml_limits = self._ml_engine.analyze(ctx)
            all_findings = builder.findings + ml_findings
        else:
            ml_limits = ()
            all_findings = builder.findings

        limitations: list[str] = []
        if not ctx.has_runtime_metrics:
            limitations.append(
                "Métricas de runtime (PodMetrics) ausentes ou incompletas: "
                "análise de utilização real limitada."
            )
        if bundle.parse_errors:
            limitations.append(
                f"{len(bundle.parse_errors)} erro(s) de parsing durante ingestão."
            )
        limitations.append(
            "Correlação workload × worknode baseada em requests configurados "
            "e snapshot de placement; não reflete consumo real nem alocação "
            "cluster-wide por nó."
        )

        limitations.extend(ml_limits)

        report = AnalysisReport(
            namespace=bundle.namespace,
            findings=_sort_findings(all_findings),
            limitations=tuple(limitations),
            workloads_analyzed=len(bundle.workloads),
            worknodes_considered=len(nodes),
            ml_enabled=ml_enabled,
        )
        return NamespaceAnalysisResult(report=report, context=ctx)
