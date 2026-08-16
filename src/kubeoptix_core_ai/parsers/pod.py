"""Parser de Pods (v1)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.models.workload import PodPlacement
from kubeoptix_core_ai.parsers.base import load_yaml_file


def _owner_workload_name(document: dict) -> str | None:
    for owner in document.get("metadata", {}).get("ownerReferences") or []:
        if not isinstance(owner, dict):
            continue
        if owner.get("kind") in ("ReplicaSet", "Deployment"):
            rs_name = str(owner.get("name", ""))
            # ReplicaSet name: <deployment>-<hash>
            parts = rs_name.rsplit("-", 1)
            if len(parts) == 2 and parts[1].isalnum():
                return parts[0]
            return rs_name or None
    return None


def parse_pod(file_path: Path) -> PodPlacement:
    """Interpreta um arquivo YAML de Pod."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "Pod":
        raise ParseError(f"kind esperado 'Pod', encontrado {kind!r}", file_path=file_path)

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    status = document.get("status") or {}

    namespace = str(metadata.get("namespace", ""))
    pod_name = str(metadata.get("name", file_path.stem))
    node_name = spec.get("nodeName")
    if node_name is not None:
        node_name = str(node_name)

    qos_class = status.get("qosClass")
    if qos_class is not None:
        qos_class = str(qos_class)

    return PodPlacement(
        pod_name=pod_name,
        workload_name=_owner_workload_name(document),
        namespace=namespace,
        node_name=node_name,
        qos_class=qos_class,
        source=source,
    )
