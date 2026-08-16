"""Parser de ConfigMaps (v1)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_analyzer.errors import ParseError
from kubeoptix_analyzer.models.inventory import ConfigMapSpec
from kubeoptix_analyzer.models.source import source_from_document
from kubeoptix_analyzer.parsers.base import load_yaml_file


def parse_configmap(file_path: Path, *, app_group: str | None = None) -> ConfigMapSpec:
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "ConfigMap":
        raise ParseError(f"kind esperado 'ConfigMap', encontrado {kind!r}", file_path=file_path)

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    data = document.get("data") or {}
    binary_data = document.get("binaryData") or {}

    keys: list[str] = []
    if isinstance(data, dict):
        keys.extend(sorted(str(k) for k in data.keys()))
    if isinstance(binary_data, dict):
        keys.extend(sorted(str(k) for k in binary_data.keys()))

    labels = metadata.get("labels") or {}
    group = app_group
    if group is None and isinstance(labels, dict) and labels.get("app"):
        group = str(labels["app"])

    return ConfigMapSpec(
        name=str(metadata.get("name", file_path.stem)),
        namespace=str(metadata.get("namespace", "")),
        app_group=group,
        keys=tuple(sorted(set(keys))),
        source=source,
    )
