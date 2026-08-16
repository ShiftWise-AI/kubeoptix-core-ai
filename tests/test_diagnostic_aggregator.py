"""Testes do agregador de diagnóstico."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_analyzer.diagnostic.aggregator import summarize_workloads, summarize_worknodes
from kubeoptix_analyzer.parsers.deployment import parse_deployment
from kubeoptix_analyzer.parsers.node import parse_node

FIXTURES = Path(__file__).parent / "fixtures"


def test_summarize_workloads_backend_fixture() -> None:
    workload = parse_deployment(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app_group="backend-acesso-app",
    )

    summary = summarize_workloads((workload,))

    assert summary.workload_count == 1
    assert summary.container_count == 1
    assert summary.replicas_desired_total == 2
    assert summary.cpu_requests.available is True
    assert summary.cpu_requests.display == "700m"  # 350m x 2 réplicas
    assert summary.cpu_limits.display == "1400m"  # 700m x 2 réplicas
    assert summary.memory_requests.display == "768Mi"  # 384Mi x 2
    assert len(summary.cpu_requests.entries) == 1
    assert summary.cpu_requests.entries[0].value_raw == "350m"


def test_summarize_worknodes_single_node() -> None:
    node = parse_node(FIXTURES / "node_osc3dv0117.yaml")
    summary = summarize_worknodes((node,))

    assert summary.worknode_count == 1
    assert summary.cpu_capacity.available is True
    assert summary.cpu_capacity.display == "8000m"
    assert summary.cpu_allocatable.display == "7500m"
    assert summary.memory_allocatable.available is True
    assert summary.memory_allocatable.entries[0].value_raw == "31715432Ki"
