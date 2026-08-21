"""Orquestração da análise determinística."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.cpu import analyze_cpu
from kubeoptix_core_ai.analysis.events import analyze_events
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.analysis.inventory import analyze_inventory
from kubeoptix_core_ai.analysis.memory import analyze_memory
from kubeoptix_core_ai.analysis.probes import analyze_probes
from kubeoptix_core_ai.analysis.qos import analyze_qos
from kubeoptix_core_ai.analysis.replicas import analyze_replicas
from kubeoptix_core_ai.analysis.resources import analyze_resources
from kubeoptix_core_ai.analysis.scheduling import analyze_scheduling
from kubeoptix_core_ai.analysis.storage import analyze_storage
from kubeoptix_core_ai.analysis.workload_node import analyze_workload_node
from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.loaders.workload_loader import WorkloadLoader
from kubeoptix_core_ai.loaders.worknode_loader import WorknodeLoader
from kubeoptix_core_ai.ml.config import MLConfig
from kubeoptix_core_ai.ml.engine import MLEngine
from kubeoptix_core_ai.ml.fleet import FleetBaseline, build_fleet_baseline
from kubeoptix_core_ai.models.finding import AnalysisReport, Finding, Severity
from kubeoptix_core_ai.models.node import WorkNode
from kubeoptix_core_ai.models.workload import NamespaceWorkloadBundle

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

_DETERMINISTIC_ANALYZERS: tuple[tuple[str, Callable[..., None]], ...] = (
    ("CPU", analyze_cpu),
    ("memória", analyze_memory),
    ("recursos", analyze_resources),
    ("QoS", analyze_qos),
    ("réplicas", analyze_replicas),
    ("probes", analyze_probes),
    ("scheduling", analyze_scheduling),
    ("armazenamento", analyze_storage),
    ("inventário", analyze_inventory),
    ("events", analyze_events),
    ("workload-node", analyze_workload_node),
)


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
        self._fleet_baseline: FleetBaseline | None | bool = False

    def _resolve_fleet_baseline(self) -> FleetBaseline | None:
        if self._fleet_baseline is False:
            try:
                fleet_workloads = self._workload_loader.load_fleet_workloads()
                self._fleet_baseline = build_fleet_baseline(fleet_workloads)
            except Exception:  # noqa: BLE001 — baseline é complementar
                self._fleet_baseline = None
        return self._fleet_baseline if self._fleet_baseline else None

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
        on_analysis_step: Callable[[int, int, str], None] | None = None,
    ) -> NamespaceAnalysisResult:
        ctx = AnalysisContext(bundle=bundle, nodes=nodes)
        builder = FindingBuilder()
        ml_enabled = enable_ml if enable_ml is not None else self._ml_config.enabled
        step_count = len(_DETERMINISTIC_ANALYZERS) + (1 if ml_enabled else 0)

        for index, (label, analyzer) in enumerate(_DETERMINISTIC_ANALYZERS, start=1):
            analyzer(ctx, builder)
            if on_analysis_step is not None:
                on_analysis_step(index, step_count, label)

        if ml_enabled:
            ml_findings, ml_limits = self._ml_engine.analyze(
                ctx,
                fleet=self._resolve_fleet_baseline(),
            )
            all_findings = builder.findings + ml_findings
            if on_analysis_step is not None:
                on_analysis_step(step_count, step_count, "ML")
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
