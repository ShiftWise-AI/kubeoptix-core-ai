"""Parser de VerticalPodAutoscaler."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.models.workload import VPASpec
from kubeoptix_core_ai.parsers.base import load_yaml_file


def parse_vpa(file_path: Path) -> VPASpec:
    """Interpreta um arquivo YAML de VerticalPodAutoscaler."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "VerticalPodAutoscaler":
        raise ParseError(
            f"kind esperado 'VerticalPodAutoscaler', encontrado {kind!r}",
            file_path=file_path,
        )

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}

    name = str(metadata.get("name", file_path.stem))
    target_ref = spec.get("targetRef") or {}
    target_workload_name = target_ref.get("name")
    if target_workload_name is not None:
        target_workload_name = str(target_workload_name)
    target_workload_kind = target_ref.get("kind")
    if target_workload_kind is not None:
        target_workload_kind = str(target_workload_kind)

    update_policy = spec.get("updatePolicy") or {}
    update_mode = update_policy.get("updateMode")
    if update_mode is not None:
        update_mode = str(update_mode)

    return VPASpec(
        name=name,
        target_workload_name=target_workload_name,
        target_workload_kind=target_workload_kind,
        update_mode=update_mode,
        source=source,
    )
