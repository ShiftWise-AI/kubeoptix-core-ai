"""Testes da seleção de manifests para KubeDiagrams."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.visualization.kubediagrams.manifests import select_architecture_manifests

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"
TRAINING_NAMESPACE_ROOT = Path(
    "/home/parraes/redhat/shiftwise-ai/base-treinamento/plfat-tbforte"
)


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
    return ns


def test_select_architecture_manifests_includes_workload_service_route(
    architecture_tree: Path,
) -> None:
    manifests = select_architecture_manifests(architecture_tree)
    paths = {path.name for path in manifests}

    assert "backend-acesso-app.yaml" in paths
    assert len(manifests) >= 3
    assert not any("replicaset" in str(path).lower() for path in manifests)


def test_select_architecture_manifests_empty_for_missing_dir(tmp_path: Path) -> None:
    assert select_architecture_manifests(tmp_path / "missing") == ()


@pytest.mark.skipif(
    not TRAINING_NAMESPACE_ROOT.is_dir(),
    reason="Base de treinamento plfat-tbforte ausente",
)
def test_select_architecture_manifests_plfat_includes_routes() -> None:
    manifests = select_architecture_manifests(TRAINING_NAMESPACE_ROOT)
    names = {path.name for path in manifests}

    assert "agenda.yaml" in names
    assert any("deployments" in str(path) for path in manifests)
    assert any("services" in str(path) for path in manifests)
    assert len(manifests) >= 30
