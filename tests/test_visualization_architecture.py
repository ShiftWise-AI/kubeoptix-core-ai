"""Testes do diagrama de arquitetura do namespace."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.markdown import MarkdownReportGenerator
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline
from kubeoptix_core_ai.visualization.datasets.architecture import (
    build_namespace_architecture_diagram,
)
from kubeoptix_core_ai.visualization.mermaid import MermaidGenerator

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def architecture_tree(tmp_path: Path) -> Path:
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

    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")
    return base


def test_architecture_diagram_focuses_on_communication(
    architecture_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=architecture_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    diagram = build_namespace_architecture_diagram(bundle)

    assert diagram is not None
    labels = {n.label for n in diagram.nodes}
    assert any(label.startswith("Pod/") for label in labels)
    assert any("inst." in label for label in labels)
    assert any(label.startswith("Service/") for label in labels)
    assert any(label.startswith("Route/") for label in labels)
    assert not any(label.startswith("Secret/") for label in labels)
    assert not any(label.startswith("Image/") for label in labels)
    assert not any(label.startswith("Registry/") for label in labels)
    assert not any(label.startswith("ConfigMap/") for label in labels)

    mermaid = MermaidGenerator().render_flowchart(diagram)
    assert "subgraph" in mermaid
    assert "Pod/" in mermaid
    assert "2/2 inst." in mermaid
    assert "Service/" in mermaid
    assert "Route/" in mermaid
    assert "Cliente externo" in mermaid
    assert "interno" in mermaid
    assert "externo" in mermaid
    assert "Secret/" not in mermaid
    assert "Image/" not in mermaid


def test_architecture_section_in_namespace_overview(
    architecture_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=architecture_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    overview_start = md.index("## 5. Visão geral do namespace")
    workloads_start = md.index("## 6. Workloads identificados")
    overview = md[overview_start:workloads_start]

    assert "### Arquitetura" in overview
    assert "**Legenda dos grupos:**" in overview
    assert "```mermaid" in overview
    assert "fluxos de comunicação" in overview


def test_architecture_without_proven_relations_returns_none(tmp_path: Path) -> None:
    base = tmp_path / "metadados"
    ns = base / "empty-ns"
    ns.mkdir(parents=True)

    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "node.yaml")

    config = AnalyzerConfig(workloads_base=base, worknodes_path=nodes)
    bundle = AssessmentPipeline(config).run("empty-ns")

    assert build_namespace_architecture_diagram(bundle) is None

    md = MarkdownReportGenerator().generate(bundle)
    assert (
        "Não foram identificadas relações de comunicação suficientes no inventário YAML"
        in md
    )
