"""Parser de PersistentVolumeClaim (v1)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_analyzer.errors import ParseError
from kubeoptix_analyzer.models.source import source_from_document
from kubeoptix_analyzer.models.storage import PersistentVolumeClaimSpec
from kubeoptix_analyzer.normalize.quantities import parse_memory_quantity
from kubeoptix_analyzer.parsers.base import load_yaml_file


def parse_pvc(file_path: Path) -> PersistentVolumeClaimSpec:
    """Interpreta um arquivo YAML de PersistentVolumeClaim."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "PersistentVolumeClaim":
        raise ParseError(
            f"kind esperado 'PersistentVolumeClaim', encontrado {kind!r}",
            file_path=file_path,
        )

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}

    name = str(metadata.get("name", file_path.stem))
    namespace = str(metadata.get("namespace", ""))

    access_modes_raw = spec.get("accessModes") or []
    access_modes = tuple(str(m) for m in access_modes_raw)

    storage_request = None
    resources = spec.get("resources") or {}
    requests = resources.get("requests") or {}
    if "storage" in requests:
        storage_request = parse_memory_quantity(
            requests["storage"],
            source=source,
            field_path="spec.resources.requests.storage",
        )

    storage_class = spec.get("storageClassName")
    if storage_class is not None:
        storage_class = str(storage_class)

    return PersistentVolumeClaimSpec(
        name=name,
        namespace=namespace,
        storage_class=storage_class,
        access_modes=access_modes,
        storage_request=storage_request,
        source=source,
    )
