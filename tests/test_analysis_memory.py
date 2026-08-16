"""Testes de análise de memória com métricas."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.analysis.memory import analyze_memory
from kubeoptix_core_ai.models.workload import NamespaceWorkloadBundle
from kubeoptix_core_ai.normalize.workload import enrich_workload
from kubeoptix_core_ai.parsers.deployment import parse_deployment
from kubeoptix_core_ai.parsers.pod_metrics import parse_pod_metrics

FIXTURES = Path(__file__).parent / "fixtures"


def test_memory_usage_above_request_finding() -> None:
    workload = enrich_workload(
        parse_deployment(
            FIXTURES / "deployment_backend_acesso_app.yaml",
            app_group="backend-acesso-app",
        )
    )
    metrics = parse_pod_metrics(FIXTURES / "pod_metrics_backend_acesso_app.yaml")
    workload = workload.model_copy(update={"metrics": (metrics,)})

    bundle = NamespaceWorkloadBundle(
        namespace="example-ns-prd",
        workloads=(workload,),
    )
    ctx = AnalysisContext(bundle=bundle, nodes=())
    builder = FindingBuilder()
    analyze_memory(ctx, builder)

    high_findings = [
        f for f in builder.findings
        if f.category == "MEM" and f.severity.value == "HIGH"
    ]
    assert len(high_findings) == 1
    assert high_findings[0].evidence[0].value is not None
    assert "841428Ki" in high_findings[0].evidence[0].value
