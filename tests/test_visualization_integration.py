"""Testes de integração das visualizações no relatório Markdown."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.markdown import MarkdownReportGenerator
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline
from kubeoptix_core_ai.visualization.builders import build_all_visualizations
from kubeoptix_core_ai.visualization.models import VisualizationStatus
from kubeoptix_core_ai.visualization.pipeline import VisualizationPipeline

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"
OTHER_NAMESPACE = "other-ns-prd"


@pytest.fixture
def full_analysis_tree(tmp_path: Path) -> Path:
    base = tmp_path / "metadados"
    ns = base / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (app / "services").mkdir(parents=True)
    (app / "routes").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app / "deployments" / "backend-acesso-app.yaml",
    )
    shutil.copy(
        FIXTURES / "service_backend_acesso_app.yaml",
        app / "services" / "backend-acesso-app.yaml",
    )
    shutil.copy(
        FIXTURES / "route_backend_acesso_app.yaml",
        app / "routes" / "backend-acesso-app.yaml",
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


def test_visualization_bundle_includes_numeric_and_flowcharts(
    full_analysis_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=full_analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    viz = VisualizationPipeline().build(bundle)

    available = [v for v in viz.visualizations if v.status == VisualizationStatus.AVAILABLE]
    assert any(v.id == "cpu_request" for v in available)
    assert any(v.id.startswith("ext_comm_") for v in available)
    assert any(v.id == "workload_node_placement" for v in available)
    for v in available:
        assert v.mermaid or v.html
        assert v.provenance


def test_markdown_contains_mermaid_blocks(
    full_analysis_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=full_analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    assert "```mermaid" in md
    assert "kubeoptix-doughnut" in md or "kubeoptix-bar-chart" in md
    assert "### Visualizações" in md
    assert "Visualização indisponível" in md or "flowchart" in md


def test_external_communication_skipped_without_routes(tmp_path: Path) -> None:
    base = tmp_path / "metadados"
    ns = base / OTHER_NAMESPACE
    app = ns / "apps" / "other-api"
    (app / "deployments").mkdir(parents=True)
    deployment = FIXTURES / "deployment_backend_acesso_app.yaml"
    content = deployment.read_text(encoding="utf-8")
    content = content.replace("example-ns-prd", OTHER_NAMESPACE)
    content = content.replace("backend-acesso-app", "other-api")
    (app / "deployments" / "other-api.yaml").write_text(content, encoding="utf-8")

    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")

    config = AnalyzerConfig(workloads_base=base, worknodes_path=nodes)
    bundle = AssessmentPipeline(config).run(OTHER_NAMESPACE)
    viz = build_all_visualizations(bundle)
    ext = next(
        (v for v in viz.visualizations if v.id == "external_communication"),
        None,
    )
    if ext is None:
        ext = next(
            (v for v in viz.visualizations if v.section == "communication_external"),
            None,
        )
    assert ext is not None
    assert ext.status == VisualizationStatus.UNAVAILABLE
