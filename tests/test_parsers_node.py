"""Testes do parser de Node."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.parsers.node import parse_node

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_node_osc3dv0117() -> None:
    path = FIXTURES / "node_osc3dv0117.yaml"
    node = parse_node(path)

    assert node.name == "osc3dv0117"
    assert node.datacenter == "diveo"
    assert node.env == "prd"
    assert node.role == "app"
    assert node.architecture == "amd64"
    assert node.ready is True
    assert node.max_pods == 250
    assert node.taints == ()

    assert node.cpu_capacity is not None
    assert node.cpu_capacity.raw == "8"
    assert node.cpu_allocatable is not None
    assert node.cpu_allocatable.raw == "7500m"
    assert node.cpu_allocatable.source.field_path == "status.allocatable.cpu"

    assert node.memory_allocatable is not None
    assert node.memory_allocatable.raw == "31715432Ki"

    assert node.source.file_path == str(path)
    assert node.source.resource_kind == "Node"
