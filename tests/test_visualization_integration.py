"""Testes de integração das visualizações no relatório Markdown."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.markdown import MarkdownReportGenerator
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline
from kubeoptix_core_ai.visualization.builders import build_all_visualizations
from kubeoptix_core_ai.visualization.kubediagrams.renderer import KubeDiagramsRenderer
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
    assets_dir = tmp_path / "viz_assets"
    viz = VisualizationPipeline().build(
        bundle,
        assets_dir=assets_dir,
        assets_prefix="viz_assets",
    )

    available = [v for v in viz.visualizations if v.status == VisualizationStatus.AVAILABLE]
    assert any(v.id == "cpu_request" for v in available)
    for v in available:
        assert v.image_relpath
        assert v.provenance

    flowcharts = [v for v in viz.visualizations if v.dataset_kind == "flowchart"]
    assert flowcharts
    assert not any(v.diagram_engine == "matplotlib" for v in flowcharts)
    for v in flowcharts:
        if v.status == VisualizationStatus.AVAILABLE:
            assert v.diagram_engine == "kubediagrams"
            assert v.image_relpath
            assert v.yaml_sources
        else:
            assert v.unavailable_reason
            assert "YAML" in v.unavailable_reason
    assert list(assets_dir.glob("*.png"))


def test_markdown_contains_png_images(
    full_analysis_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=full_analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    assets_dir = tmp_path / "assets"
    md = MarkdownReportGenerator().generate(bundle, assets_dir=assets_dir)

    assert "![CPU request por workload]" in md or ".png)" in md
    assert "### Visualizações" in md
    assert list(assets_dir.glob("*.png"))


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


def test_flowcharts_never_fallback_to_matplotlib(
    full_analysis_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AnalyzerConfig(
        workloads_base=full_analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    assets_dir = tmp_path / "viz_assets_no_kd"

    monkeypatch.setattr(
        KubeDiagramsRenderer,
        "render_manifests",
        lambda self, viz_id, manifests: None,
    )

    viz = VisualizationPipeline().build(
        bundle,
        assets_dir=assets_dir,
        assets_prefix="viz_assets_no_kd",
    )

    flowcharts = [v for v in viz.visualizations if v.dataset_kind == "flowchart"]
    assert flowcharts
    assert all(v.status == VisualizationStatus.UNAVAILABLE for v in flowcharts)
    assert not any(v.diagram_engine == "matplotlib" for v in flowcharts)
