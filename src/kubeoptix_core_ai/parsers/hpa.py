"""Parser de HorizontalPodAutoscaler (autoscaling/v2)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.models.workload import HPASpec
from kubeoptix_core_ai.parsers.base import load_yaml_file


def parse_hpa(file_path: Path) -> HPASpec:
    """Interpreta um arquivo YAML de HorizontalPodAutoscaler."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "HorizontalPodAutoscaler":
        raise ParseError(
            f"kind esperado 'HorizontalPodAutoscaler', encontrado {kind!r}",
            file_path=file_path,
        )

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}

    name = str(metadata.get("name", file_path.stem))
    min_replicas = spec.get("minReplicas")
    max_replicas = spec.get("maxReplicas")
    if min_replicas is not None:
        min_replicas = int(min_replicas)
    if max_replicas is not None:
        max_replicas = int(max_replicas)

    target_ref = spec.get("scaleTargetRef") or {}
    target_workload_name = target_ref.get("name")
    if target_workload_name is not None:
        target_workload_name = str(target_workload_name)

    metric_descriptions: list[str] = []
    for metric in spec.get("metrics") or []:
        if not isinstance(metric, dict):
            continue
        metric_type = metric.get("type")
        if metric_type == "Resource":
            resource = metric.get("resource") or {}
            resource_name = resource.get("name")
            target = resource.get("target") or {}
            utilization = target.get("averageUtilization")
            if resource_name and utilization is not None:
                metric_descriptions.append(f"{resource_name}:{utilization}%")
            elif resource_name:
                metric_descriptions.append(str(resource_name))
        else:
            metric_descriptions.append(str(metric_type))

    return HPASpec(
        name=name,
        min_replicas=min_replicas,
        max_replicas=max_replicas,
        target_workload_name=target_workload_name,
        metrics=metric_descriptions,
        source=source,
    )
