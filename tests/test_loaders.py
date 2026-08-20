"""Testes dos carregadores com fixtures locais."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.errors import ConfigurationError
from kubeoptix_core_ai.loaders.workload_loader import WorkloadLoader
from kubeoptix_core_ai.loaders.worknode_loader import WorknodeLoader
from kubeoptix_core_ai.normalize.qos import QOS_BURSTABLE

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def mini_namespace_tree(tmp_path: Path) -> Path:
    """Monta árvore mínima espelhando estrutura real de metadados."""
    ns_root = tmp_path / EXAMPLE_NAMESPACE
    app_dir = ns_root / "apps" / "backend-acesso-app"
    (app_dir / "deployments").mkdir(parents=True)
    (app_dir / "hpa").mkdir(parents=True)

    shutil.copy(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app_dir / "deployments" / "backend-acesso-app.yaml",
    )

    pods_dir = ns_root / "resources" / "pods"
    pods_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_backend_acesso_app.yaml", pods_dir / "pod.yaml")

    metrics_dir = ns_root / "resources" / "pods.metrics.k8s.io"
    metrics_dir.mkdir(parents=True)
    shutil.copy(
        FIXTURES / "pod_metrics_backend_acesso_app.yaml",
        metrics_dir / "metrics.yaml",
    )

    hpa_content = """apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-acesso-app
  namespace: example-ns-prd
spec:
  minReplicas: 2
  maxReplicas: 5
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend-acesso-app
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
"""
    (app_dir / "hpa" / "backend-acesso-app.yaml").write_text(hpa_content, encoding="utf-8")

    return tmp_path


def test_workload_loader_integrates_placements_and_metrics(
    mini_namespace_tree: Path,
) -> None:
    config = AnalyzerConfig(workloads_base=mini_namespace_tree)
    bundle = WorkloadLoader(config).load_namespace(EXAMPLE_NAMESPACE)

    assert bundle.workload_count == 1
    assert not bundle.parse_errors

    workload = bundle.workloads[0]
    assert workload.name == "backend-acesso-app"
    assert workload.qos_class == QOS_BURSTABLE
    assert workload.total_cpu_request_per_pod_millicores == 350.0
    assert len(workload.placements) == 1
    assert workload.placements[0].node_name == "osc3dv0117"
    assert len(workload.metrics) == 1
    assert workload.hpa is not None
    assert workload.hpa.min_replicas == 2
    assert workload.hpa.metrics == ["cpu:70%"]


def test_workload_loader_reports_file_progress(
    mini_namespace_tree: Path,
) -> None:
    config = AnalyzerConfig(workloads_base=mini_namespace_tree)
    ticks: list[tuple[int, int]] = []

    WorkloadLoader(config).load_namespace(
        EXAMPLE_NAMESPACE,
        on_file_processed=lambda processed, total: ticks.append((processed, total)),
    )

    assert ticks
    assert ticks[0][0] == 1
    assert ticks[-1][0] == ticks[-1][1]
    assert all(total == ticks[0][1] for _, total in ticks)
    assert all(processed <= total for processed, total in ticks)


def test_worknode_loader(tmp_path: Path) -> None:
    nodes_dir = tmp_path / "worknodes"
    nodes_dir.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes_dir / "osc3dv0117.yaml")

    config = AnalyzerConfig(worknodes_path=nodes_dir)
    bundle = WorknodeLoader(config).load()

    assert bundle.node_count == 1
    assert bundle.nodes[0].name == "osc3dv0117"
    assert not bundle.parse_errors


def test_workload_loader_missing_namespace(tmp_path: Path) -> None:
    config = AnalyzerConfig(workloads_base=tmp_path)
    with pytest.raises(ConfigurationError):
        WorkloadLoader(config).load_namespace("inexistente")


def test_namespace_path_rejects_traversal(tmp_path: Path) -> None:
    config = AnalyzerConfig(workloads_base=tmp_path)
    with pytest.raises(ConfigurationError):
        config.namespace_path("../etc")
    with pytest.raises(ConfigurationError):
        config.namespace_path("foo/bar")
