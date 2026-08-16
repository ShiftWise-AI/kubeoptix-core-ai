"""Parser de PodMetrics (metrics.k8s.io)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_analyzer.errors import ParseError
from kubeoptix_analyzer.models.metrics import ContainerMetrics, PodMetricsSnapshot
from kubeoptix_analyzer.models.source import source_from_document
from kubeoptix_analyzer.normalize.quantities import parse_cpu_quantity, parse_memory_quantity
from kubeoptix_analyzer.parsers.base import load_yaml_file


def parse_pod_metrics(file_path: Path) -> PodMetricsSnapshot:
    """Interpreta um arquivo YAML de PodMetrics."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "PodMetrics":
        raise ParseError(f"kind esperado 'PodMetrics', encontrado {kind!r}", file_path=file_path)

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}

    namespace = str(metadata.get("namespace", ""))
    pod_name = str(metadata.get("name", file_path.stem))

    timestamp = document.get("timestamp")
    if timestamp is not None:
        timestamp = str(timestamp)

    window = document.get("window")
    window_seconds: float | None = None
    if window is not None:
        text = str(window).rstrip("s")
        try:
            window_seconds = float(text)
        except ValueError:
            window_seconds = None

    containers: list[ContainerMetrics] = []
    for idx, container_data in enumerate(document.get("containers") or []):
        if not isinstance(container_data, dict):
            continue
        container_name = str(container_data.get("name", f"container-{idx}"))
        usage = container_data.get("usage") or {}
        base = f"containers[{idx}].usage"

        cpu_usage = None
        memory_usage = None

        if "cpu" in usage:
            cpu_usage = parse_cpu_quantity(
                usage["cpu"],
                source=source,
                field_path=f"{base}.cpu",
            )
        if "memory" in usage:
            memory_usage = parse_memory_quantity(
                usage["memory"],
                source=source,
                field_path=f"{base}.memory",
            )

        containers.append(
            ContainerMetrics(
                container_name=container_name,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
            )
        )

    return PodMetricsSnapshot(
        pod_name=pod_name,
        namespace=namespace,
        containers=tuple(containers),
        timestamp=timestamp,
        window_seconds=window_seconds,
        source=source,
    )
