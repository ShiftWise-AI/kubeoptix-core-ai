"""Utilitários de rastreabilidade para visualizações."""

from __future__ import annotations

from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef
from kubeoptix_core_ai.visualization.models import EvidenceKind, ProvenanceRef


def from_field_ref(field: FieldRef, *, kind: EvidenceKind = EvidenceKind.OBSERVED) -> ProvenanceRef:
    return ProvenanceRef(
        kind=kind,
        file_path=field.file_path,
        field_path=field.field_path,
        description=field.raw_value,
    )


def from_source(
    source: DataSourceRef,
    *,
    kind: EvidenceKind = EvidenceKind.OBSERVED,
    field_path: str | None = None,
    description: str | None = None,
) -> ProvenanceRef:
    return ProvenanceRef(
        kind=kind,
        file_path=source.file_path,
        field_path=field_path,
        resource_kind=source.resource_kind,
        resource_name=source.resource_name,
        description=description,
    )


def calculated(description: str, *, sources: tuple[DataSourceRef, ...] = ()) -> ProvenanceRef:
    file_path = sources[0].file_path if sources else None
    return ProvenanceRef(
        kind=EvidenceKind.CALCULATED,
        file_path=file_path,
        description=description,
    )


def matched(description: str, *, source: DataSourceRef | None = None) -> ProvenanceRef:
    return ProvenanceRef(
        kind=EvidenceKind.MATCHED,
        file_path=source.file_path if source else None,
        resource_kind=source.resource_kind if source else None,
        resource_name=source.resource_name if source else None,
        description=description,
    )
