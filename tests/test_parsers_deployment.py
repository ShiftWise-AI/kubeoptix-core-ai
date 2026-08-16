"""Testes do parser de Deployment."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubeoptix_core_ai.parsers.deployment import parse_deployment

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_deployment_backend_acesso_app() -> None:
    path = FIXTURES / "deployment_backend_acesso_app.yaml"
    workload = parse_deployment(path, app_group="backend-acesso-app")

    assert workload.namespace == "example-ns-prd"
    assert workload.name == "backend-acesso-app"
    assert workload.app_group == "backend-acesso-app"
    assert workload.kind == "Deployment"
    assert workload.replicas_desired == 2
    assert workload.replicas_ready == 2
    assert workload.node_selector == {"env": "prd", "type": "app"}

    assert len(workload.containers) == 1
    container = workload.containers[0]
    assert container.name == "backend-acesso-app"
    assert container.cpu_request is not None
    assert container.cpu_request.raw == "350m"
    assert container.cpu_request.source.field_path.endswith("resources.requests.cpu")
    assert container.cpu_limit is not None
    assert container.cpu_limit.raw == "700m"
    assert container.memory_request is not None
    assert container.memory_request.raw == "384Mi"
    assert container.memory_limit is not None
    assert container.memory_limit.raw == "2Gi"
    assert container.readiness_probe is None
    assert container.liveness_probe is None

    assert workload.source.file_path == str(path)
    assert workload.source.resource_kind == "Deployment"
