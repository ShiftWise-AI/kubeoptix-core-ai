"""Parser de Events (core/v1 e events.k8s.io)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.inventory import EventSpec
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.parsers.base import load_yaml_file


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def parse_event(file_path: Path) -> EventSpec:
    """Interpreta um arquivo YAML de Event."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "Event":
        raise ParseError(f"kind esperado 'Event', encontrado {kind!r}", file_path=file_path)

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    involved = document.get("involvedObject") or {}
    if not isinstance(involved, dict):
        involved = {}

    name = str(metadata.get("name", file_path.stem))
    namespace = str(
        metadata.get("namespace")
        or involved.get("namespace")
        or source.namespace
        or ""
    )

    return EventSpec(
        name=name,
        namespace=namespace,
        event_type=str(document["type"]) if document.get("type") is not None else None,
        reason=str(document["reason"]) if document.get("reason") is not None else None,
        message=str(document["message"]) if document.get("message") is not None else None,
        count=_optional_int(document.get("count")),
        involved_kind=str(involved["kind"]) if involved.get("kind") is not None else None,
        involved_name=str(involved["name"]) if involved.get("name") is not None else None,
        first_timestamp=(
            str(document["firstTimestamp"])
            if document.get("firstTimestamp") is not None
            else None
        ),
        last_timestamp=(
            str(document["lastTimestamp"])
            if document.get("lastTimestamp") is not None
            else None
        ),
        source=source,
    )
