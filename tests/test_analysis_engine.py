"""Testes do motor de análise."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_analyzer.analysis.engine import AnalysisEngine
from kubeoptix_analyzer.config import AnalyzerConfig
from kubeoptix_analyzer.models.finding import Severity

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def analysis_tree(tmp_path: Path) -> Path:
    base = tmp_path / "metadados"
    ns = base / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app / "deployments" / "backend-acesso-app.yaml",
    )
    pods = ns / "resources" / "pods"
    pods.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_backend_acesso_app.yaml", pods / "pod.yaml")
    metrics = ns / "resources" / "pods.metrics.k8s.io"
    metrics.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_metrics_backend_acesso_app.yaml", metrics / "m.yaml")

    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")
    return base


def test_analysis_engine_mini_tree(analysis_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    report = AnalysisEngine(config).analyze_namespace(EXAMPLE_NAMESPACE)

    assert report.workloads_analyzed == 1
    assert report.worknodes_considered == 1
    assert report.finding_count > 0

    categories = {f.category for f in report.findings}
    assert "PROBE" in categories
    assert "MEM" in categories
    assert "CPU" in categories

    for finding in report.findings:
        assert finding.id.startswith("RES-") or finding.id.startswith("ML-")
        assert finding.severity in Severity
        assert finding.analysis
        assert finding.confidence
