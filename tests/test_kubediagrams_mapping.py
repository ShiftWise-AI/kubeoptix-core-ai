"""Testes do mapeamento YAML → diagrama."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline
from kubeoptix_core_ai.visualization.kubediagrams.mapping import (
    DIAGRAM_YAML_MAPPING,
    DiagramKind,
    manifest_index_for,
    manifests_for_external_route,
    manifests_for_namespace_architecture,
)

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"
TRAINING_ROOT = Path("/home/parraes/redhat/shiftwise-ai/base-treinamento/plfat-tbforte")


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
    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")
    return base


def test_diagram_yaml_mapping_documents_all_kinds() -> None:
    assert set(DIAGRAM_YAML_MAPPING) == set(DiagramKind)


def test_manifests_for_external_route(architecture_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=architecture_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    route = bundle.context.routes[0]
    index = manifest_index_for(bundle)
    manifests = manifests_for_external_route(route, bundle, index)

    assert len(manifests) >= 2
    names = {path.stem for path in manifests}
    assert route.name in names
    assert route.target_service in names


@pytest.mark.skipif(not TRAINING_ROOT.is_dir(), reason="plfat-tbforte ausente")
def test_manifests_for_namespace_architecture_plfat() -> None:
    config = AnalyzerConfig(
        workloads_base=TRAINING_ROOT.parent,
        worknodes_path=TRAINING_ROOT / "worknodes",
    )
    bundle = AssessmentPipeline(config).run("plfat-tbforte")
    manifests = manifests_for_namespace_architecture(bundle)
    assert len(manifests) >= 48
