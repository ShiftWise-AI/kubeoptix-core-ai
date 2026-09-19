"""Testes do diagrama de arquitetura do namespace."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.analysis.namespace_partition import propose_namespace_partition_from_context
from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.markdown import MarkdownReportGenerator
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline
from kubeoptix_core_ai.visualization.datasets.architecture import (
    build_namespace_architecture_diagram,
    build_proposed_namespace_architecture_diagram,
)
from kubeoptix_core_ai.visualization.png.export_config import layout_profile_for_viz
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


def test_architecture_section_in_namespace_overview(
    architecture_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=architecture_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    assets_dir = tmp_path / "assets"
    md = MarkdownReportGenerator().generate(bundle, assets_dir=assets_dir)

    overview_start = md.index("## 3. Arquitetura reversa")
    cpu_start = md.index("## 4. Recursos de CPU e memória")
    overview = md[overview_start:cpu_start]

    assert "## 3. Arquitetura reversa" in md
    assert "## 4. Recursos de CPU e memória" in md
    assert "### Arquitetura reversa (fallback textual)" in overview or "Fluxo de entrada" in overview
    assert (
        "Diagrama gerado a partir dos manifests YAML" in overview
        or "Diagrama de arquitetura indisponível" in overview
        or "Fluxo de entrada, Service e dependências internas" in overview
    )
    if (
        "![Arquitetura do namespace]" in overview
        or 'alt="Arquitetura do namespace"' in overview
    ):
        assert (assets_dir / "namespace_architecture.png").is_file()


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


def _write_deployment(path: Path, name: str, namespace: str, *, kind: str = "Deployment") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""apiVersion: apps/v1
kind: {kind}
metadata:
  name: {name}
  namespace: {namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
      - name: app
        image: example/{name}:1
        resources:
          requests:
            cpu: 10m
            memory: 32Mi
""",
        encoding="utf-8",
    )


def _write_service(path: Path, name: str, namespace: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {namespace}
spec:
  selector:
    app: {name}
  ports:
  - port: 8080
    targetPort: 8080
""",
        encoding="utf-8",
    )


def _write_route(path: Path, name: str, namespace: str, target: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {name}
  namespace: {namespace}
spec:
  host: {name}.example.com
  to:
    kind: Service
    name: {target}
  tls:
    termination: edge
""",
        encoding="utf-8",
    )


@pytest.fixture
def crowded_namespace_tree(tmp_path: Path) -> Path:
    base = tmp_path / "metadados"
    ns_name = "crowded-ns"
    ns = base / ns_name
    frontend = ns / "apps" / "frontend"
    batch = ns / "apps" / "batch"
    for index in range(3):
        _write_deployment(
            frontend / "deployments" / f"web-{index}.yaml",
            f"web-{index}",
            ns_name,
        )
        _write_service(
            frontend / "services" / f"web-{index}.yaml",
            f"web-{index}",
            ns_name,
        )
        _write_deployment(
            batch / "deployments" / f"job-{index}.yaml",
            f"job-{index}",
            ns_name,
        )
    _write_route(frontend / "routes" / "web-public.yaml", "web-public", ns_name, "web-0")
    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")
    return base


def test_architecture_section_suggests_namespace_split(
    crowded_namespace_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=crowded_namespace_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run("crowded-ns")
    partition = propose_namespace_partition_from_context(bundle.context)
    assert partition.should_split is True
    assert any(f.category == "ARCH" for f in bundle.analysis.findings)

    md = MarkdownReportGenerator().generate(bundle)
    overview_start = md.index("## 3. Arquitetura reversa")
    cpu_start = md.index("## 4. Recursos de CPU e memória")
    overview = md[overview_start:cpu_start]
    assert "### Redistribuição sugerida do namespace" in overview or "Namespace sugerido" in overview
    assert "Grupo de aplicação" in overview
    assert "Namespace sugerido" in overview
    for group in partition.groups:
        assert f"`{group.suggested_name}`" in overview


def test_proposed_architecture_diagram_keeps_group_workloads(
    crowded_namespace_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=crowded_namespace_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run("crowded-ns")
    partition = propose_namespace_partition_from_context(bundle.context)
    assert partition.groups
    proposal = partition.groups[0]
    diagram = build_proposed_namespace_architecture_diagram(bundle, proposal)
    if diagram is None:
        return
    pod_labels = [node.label for node in diagram.nodes if node.label.startswith("Pod/")]
    for label in pod_labels:
        assert any(name in label for name in proposal.workload_names)


def test_proposed_namespace_viz_uses_architecture_layout() -> None:
    assert layout_profile_for_viz("proposed_ns_frontend") == "architecture"
    assert layout_profile_for_viz("cpu_request") == "diagram"
