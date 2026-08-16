"""Testes do runner de diagnóstico."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_analyzer.config import AnalyzerConfig
from kubeoptix_analyzer.diagnostic.runner import DiagnosticRunner

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def diagnostic_tree(tmp_path: Path) -> Path:
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


def test_diagnostic_runner_mini_tree(diagnostic_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=diagnostic_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    report = DiagnosticRunner(config).run(EXAMPLE_NAMESPACE)

    assert report.namespace == EXAMPLE_NAMESPACE
    assert report.files_found_count == 3
    assert report.files_to_process_count == 3
    assert report.files_processed_count == 3
    assert not report.parse_errors
    assert report.workloads.workload_count == 1
    assert report.workloads.container_count == 1
    assert report.workloads.replicas_desired_total == 2
    assert report.workloads.cpu_requests.display == "700m"
    assert report.worknodes.worknode_count == 1
