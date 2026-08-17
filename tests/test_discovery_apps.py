"""Testes de descoberta da árvore apps/<app_group>/."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.discovery.apps import discover_apps_tree
from kubeoptix_core_ai.discovery.scanner import discover_namespace
from kubeoptix_core_ai.loaders.workload_loader import WorkloadLoader

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def namespace_with_apps_pods(tmp_path: Path) -> Path:
    """Namespace com Pod e PodMetrics sob apps/, não em resources/."""
    ns_root = tmp_path / EXAMPLE_NAMESPACE
    app = ns_root / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app / "deployments" / "backend-acesso-app.yaml",
    )

    pods_dir = app / "pods"
    pods_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_backend_acesso_app.yaml", pods_dir / "pod.yaml")

    metrics_dir = app / "pods.metrics.k8s.io"
    metrics_dir.mkdir(parents=True)
    shutil.copy(
        FIXTURES / "pod_metrics_backend_acesso_app.yaml",
        metrics_dir / "metrics.yaml",
    )

    return ns_root


def test_discover_apps_tree_finds_pods_and_metrics(namespace_with_apps_pods: Path) -> None:
    tree = discover_apps_tree(namespace_with_apps_pods)

    assert len(tree.get("workload", ())) == 1
    assert len(tree.get("pod", ())) == 1
    assert len(tree.get("pod_metrics", ())) == 1


def test_discover_namespace_merges_apps_and_resources(namespace_with_apps_pods: Path) -> None:
    paths = discover_namespace(namespace_with_apps_pods)

    assert len(paths.workload_files) == 1
    assert len(paths.pod_files) == 1
    assert len(paths.pod_metrics_files) == 1
    assert all("apps" in str(p) for p in paths.pod_files)


def test_loader_uses_pods_from_apps(namespace_with_apps_pods: Path) -> None:
    config = AnalyzerConfig(workloads_base=namespace_with_apps_pods.parent)
    bundle = WorkloadLoader(config).load_namespace(EXAMPLE_NAMESPACE)

    assert bundle.workload_count == 1
    workload = bundle.workloads[0]
    assert len(workload.placements) == 1
    assert len(workload.metrics) == 1
    assert workload.qos_class == "Burstable"


def test_dedupe_yaml_by_stem_prefers_resources(tmp_path: Path) -> None:
    from kubeoptix_core_ai.discovery.apps import dedupe_yaml_by_stem

    apps_file = tmp_path / "apps" / "my-app" / "deployments" / "foo.yaml"
    res_file = tmp_path / "resources" / "deployments.apps" / "foo.yaml"
    apps_file.parent.mkdir(parents=True)
    res_file.parent.mkdir(parents=True)
    apps_file.write_text("kind: Deployment\nmetadata:\n  name: foo\n", encoding="utf-8")
    res_file.write_text("kind: Deployment\nmetadata:\n  name: foo\n", encoding="utf-8")

    result = dedupe_yaml_by_stem((apps_file, res_file))
    assert len(result) == 1
    assert result[0] == res_file
