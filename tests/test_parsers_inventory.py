"""Testes dos parsers de inventário."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.parsers.configmap import parse_configmap
from kubeoptix_core_ai.parsers.route import parse_route
from kubeoptix_core_ai.parsers.service import parse_service

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_service() -> None:
    svc = parse_service(FIXTURES / "service_backend_acesso_app.yaml")
    assert svc.name == "backend-acesso-app"
    assert svc.service_type == "ClusterIP"
    assert svc.cluster_ip == "10.42.31.169"
    assert len(svc.ports) == 1
    assert svc.ports[0].port == 8081


def test_parse_route_tls_policy() -> None:
    route = parse_route(FIXTURES / "route_backend_acesso_app.yaml")
    assert route.name == "backend-acesso-app"
    assert route.tls_insecure_policy == "Allow"
    assert route.target_service == "backend-acesso-app"


def test_parse_configmap_keys_only() -> None:
    cm = parse_configmap(FIXTURES / "configmap_frontend.yaml")
    assert cm.name == "example-frontend"
    assert cm.keys == ("PROJECT",)
