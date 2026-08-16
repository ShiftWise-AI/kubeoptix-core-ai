"""Testes de inventário de arquivos."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.discovery.inventory import scan_namespace_files

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def namespace_with_noise(tmp_path: Path) -> Path:
    """Namespace mínimo com arquivos processáveis e ignorados."""
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app / "deployments" / "backend-acesso-app.yaml",
    )

    # ReplicaSet histórico (deve ser ignorado)
    rs_dir = app / "replicasets"
    rs_dir.mkdir()
    (rs_dir / "rs.yaml").write_text("kind: ReplicaSet\n", encoding="utf-8")

    # PackageManifest (deve ser ignorado)
    pm_dir = ns / "resources" / "packagemanifests.packages.operators.coreos.com"
    pm_dir.mkdir(parents=True)
    (pm_dir / "operator.yaml").write_text("kind: PackageManifest\n", encoding="utf-8")

    # Pod processável
    pods = ns / "resources" / "pods"
    pods.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_backend_acesso_app.yaml", pods / "pod.yaml")

    # __sem_app__ (deve ser ignorado)
    sem = ns / "apps" / "__sem_app__" / "configmaps"
    sem.mkdir(parents=True)
    (sem / "kube-root-ca.crt.yaml").write_text("kind: ConfigMap\n", encoding="utf-8")

    return ns


def test_scan_classifies_processable_and_ignored(namespace_with_noise: Path) -> None:
    inventory = scan_namespace_files(namespace_with_noise)

    assert inventory.namespace == EXAMPLE_NAMESPACE
    assert inventory.files_found_count == 5
    assert inventory.files_to_process_count == 2
    assert inventory.files_ignored_count == 3

    processable_names = {Path(p).name for p in inventory.files_to_process}
    assert "backend-acesso-app.yaml" in processable_names
    assert "pod.yaml" in processable_names

    reasons = {Path(ig.file_path).name: ig.reason for ig in inventory.files_ignored}
    assert "rs.yaml" in reasons
    assert "ReplicaSet" in reasons["rs.yaml"]
    assert "operator.yaml" in reasons
    assert "OLM" in reasons["operator.yaml"] or "catalogo" in reasons["operator.yaml"]
