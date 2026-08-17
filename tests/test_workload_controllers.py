"""Testes do parser genérico de workloads e correlação."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.loaders.workload_loader import WorkloadLoader
from kubeoptix_core_ai.parsers.workload_controller import parse_workload_controller

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"

CRONJOB_YAML = """apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-backup
  namespace: example-ns-prd
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: backup:latest
            resources:
              requests:
                cpu: 50m
                memory: 64Mi
          restartPolicy: OnFailure
"""

PDB_YAML = """apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: backend-pdb
  namespace: example-ns-prd
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: backend-acesso-app
"""

STATEFULSET_YAML = """apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-cluster
  namespace: example-ns-prd
spec:
  replicas: 3
  selector:
    matchLabels:
      app: redis-cluster
  serviceName: redis-cluster
  template:
    metadata:
      labels:
        app: redis-cluster
    spec:
      containers:
      - name: redis
        image: redis:7
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
status:
  readyReplicas: 3
  replicas: 3
"""


@pytest.fixture
def multi_workload_tree(tmp_path: Path) -> Path:
    """Namespace com Deployment, StatefulSet e CronJob."""
    ns_root = tmp_path / EXAMPLE_NAMESPACE
    app = ns_root / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app / "deployments" / "backend-acesso-app.yaml",
    )

    stateful_app = ns_root / "apps" / "redis"
    (stateful_app / "statefulsets").mkdir(parents=True)
    (stateful_app / "statefulsets" / "redis-cluster.yaml").write_text(
        STATEFULSET_YAML, encoding="utf-8"
    )

    cron_app = ns_root / "apps" / "backup"
    (cron_app / "cronjobs").mkdir(parents=True)
    (cron_app / "cronjobs" / "nightly-backup.yaml").write_text(
        CRONJOB_YAML, encoding="utf-8"
    )

    pdb_dir = ns_root / "resources" / "poddisruptionbudgets.policy"
    pdb_dir.mkdir(parents=True)
    (pdb_dir / "backend-pdb.yaml").write_text(PDB_YAML, encoding="utf-8")

    pods_dir = ns_root / "resources" / "pods"
    pods_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_backend_acesso_app.yaml", pods_dir / "pod.yaml")

    return tmp_path


def test_parse_statefulset() -> None:
    path = FIXTURES / "statefulset_redis.yaml"
    workload = parse_workload_controller(path, app_group="redis")
    assert workload.kind == "StatefulSet"
    assert workload.name == "redis-cluster"
    assert workload.replicas_desired == 3
    assert workload.replicas_ready == 3
    assert workload.containers[0].cpu_request is not None


def test_parse_cronjob() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(CRONJOB_YAML)
        path = Path(f.name)

    workload = parse_workload_controller(path, app_group="backup")
    assert workload.kind == "CronJob"
    assert workload.schedule == "0 2 * * *"
    assert len(workload.containers) == 1


def test_loader_discovers_multiple_workload_kinds(multi_workload_tree: Path) -> None:
    config = AnalyzerConfig(workloads_base=multi_workload_tree)
    bundle = WorkloadLoader(config).load_namespace(EXAMPLE_NAMESPACE)

    kinds = {w.kind for w in bundle.workloads}
    assert "Deployment" in kinds
    assert "StatefulSet" in kinds
    assert "CronJob" in kinds
    assert "ReplicaSet" not in kinds
    assert bundle.workload_count == 3

    deployment = next(w for w in bundle.workloads if w.kind == "Deployment")
    assert deployment.pdb is not None
    assert deployment.pdb.name == "backend-pdb"
    assert len(deployment.placements) == 1

    statefulset = next(w for w in bundle.workloads if w.kind == "StatefulSet")
    assert statefulset.name == "redis-cluster"
    assert statefulset.replicas_desired == 3
