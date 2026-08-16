"""Testes de utilitários da camada de análise."""

from __future__ import annotations

from kubeoptix_analyzer.analysis.helpers import (
    aggregate_runtime_usage,
    derive_scheduling_pool_selector,
    node_role_label,
)
from kubeoptix_analyzer.models.node import WorkNode
from kubeoptix_analyzer.models.source import DataSourceRef
from kubeoptix_analyzer.models.workload import Workload


def _workload(name: str, selector: dict[str, str]) -> Workload:
    return Workload(
        namespace="ns",
        name=name,
        app_group=name,
        kind="Deployment",
        replicas_desired=2,
        node_selector=selector,
        source=DataSourceRef(
            file_path="/tmp/d.yaml",
            resource_kind="Deployment",
            resource_name=name,
            namespace="ns",
        ),
    )


def test_derive_scheduling_pool_selector_majority() -> None:
    workloads = (
        _workload("backend-a", {"env": "prd", "type": "app"}),
        _workload("backend-b", {"env": "prd", "type": "app"}),
        _workload("frontend", {}),
    )
    selector = derive_scheduling_pool_selector(workloads)
    assert selector == {"env": "prd", "type": "app"}


def test_node_role_label() -> None:
    node = WorkNode(
        name="n1",
        labels={"type": "app", "env": "prd"},
        role="app",
        env="prd",
        source=DataSourceRef(
            file_path="/tmp/n.yaml",
            resource_kind="Node",
            resource_name="n1",
        ),
    )
    assert node_role_label(node) == "app/prd"


def test_aggregate_runtime_usage_empty() -> None:
    cpu, mem = aggregate_runtime_usage(())
    assert cpu is None
    assert mem is None
