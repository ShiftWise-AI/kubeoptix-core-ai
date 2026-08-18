"""Parser de PodDisruptionBudget."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.models.workload import PDBSpec
from kubeoptix_core_ai.parsers.base import load_yaml_file


def parse_pdb(file_path: Path) -> PDBSpec:
    """Interpreta um arquivo YAML de PodDisruptionBudget."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "PodDisruptionBudget":
        raise ParseError(
            f"kind esperado 'PodDisruptionBudget', encontrado {kind!r}",
            file_path=file_path,
        )

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}

    name = str(metadata.get("name", file_path.stem))
    min_available = spec.get("minAvailable")
    max_unavailable = spec.get("maxUnavailable")

    selector_raw = spec.get("selector") or {}
    match_labels = selector_raw.get("matchLabels") or {}
    if not isinstance(match_labels, dict):
        match_labels = {}
    selector = {str(k): str(v) for k, v in match_labels.items()}

    return PDBSpec(
        name=name,
        min_available=min_available,
        max_unavailable=max_unavailable,
        selector=selector,
        source=source,
    )
