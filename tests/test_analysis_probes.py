"""Testes de análise de probes."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubeoptix_analyzer.analysis.context import AnalysisContext
from kubeoptix_analyzer.analysis.findings_builder import FindingBuilder
from kubeoptix_analyzer.analysis.probes import analyze_probes
from kubeoptix_analyzer.config import AnalyzerConfig
from kubeoptix_analyzer.loaders.workload_loader import WorkloadLoader
from kubeoptix_analyzer.models.finding import Severity
from kubeoptix_analyzer.models.node import WorkNodeBundle
from kubeoptix_analyzer.models.workload import NamespaceWorkloadBundle
from kubeoptix_analyzer.parsers.deployment import parse_deployment

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def backend_workload():
    return parse_deployment(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app_group="backend-acesso-app",
    )


def test_probes_missing_on_backend(backend_workload) -> None:
    bundle = NamespaceWorkloadBundle(
        namespace="example-ns-prd",
        workloads=(backend_workload,),
    )
    ctx = AnalysisContext(bundle=bundle, nodes=())
    builder = FindingBuilder()
    analyze_probes(ctx, builder)

    categories = {f.category for f in builder.findings}
    assert "PROBE" in categories

    readiness = [f for f in builder.findings if "readiness" in f.analysis.lower()]
    assert readiness
    assert readiness[0].severity == Severity.HIGH  # 2 réplicas
    assert readiness[0].workload == "backend-acesso-app"
    assert readiness[0].evidence
    assert readiness[0].evidence[0].file_path
