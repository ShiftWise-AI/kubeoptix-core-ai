"""Testes do parser de PodMetrics."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.parsers.pod_metrics import parse_pod_metrics

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_pod_metrics_backend_acesso_app() -> None:
    path = FIXTURES / "pod_metrics_backend_acesso_app.yaml"
    snapshot = parse_pod_metrics(path)

    assert snapshot.namespace == "example-ns-prd"
    assert snapshot.pod_name == "backend-acesso-app-7dd76c8686-g7z2n"
    assert snapshot.timestamp == "2026-08-10T21:15:15Z"
    assert snapshot.window_seconds == 15.268

    assert len(snapshot.containers) == 1
    metrics = snapshot.containers[0]
    assert metrics.container_name == "backend-acesso-app"
    assert metrics.cpu_usage is not None
    assert metrics.cpu_usage.raw == "6365928n"
    assert metrics.cpu_usage.source.field_path == "containers[0].usage.cpu"
    assert metrics.memory_usage is not None
    assert metrics.memory_usage.raw == "841428Ki"

    assert snapshot.source.file_path == str(path)
    assert snapshot.source.resource_kind == "PodMetrics"
