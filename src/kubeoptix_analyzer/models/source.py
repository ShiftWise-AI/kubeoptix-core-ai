"""Rastreabilidade de origem dos dados."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DataSourceRef(BaseModel):
    """Referência a um recurso Kubernetes em um arquivo."""

    model_config = ConfigDict(frozen=True)

    file_path: str
    resource_kind: str
    resource_name: str
    namespace: str | None = None


class FieldRef(BaseModel):
    """Referência a um campo específico dentro de um arquivo."""

    model_config = ConfigDict(frozen=True)

    file_path: str
    field_path: str
    raw_value: str | None = None

    @classmethod
    def from_source(
        cls,
        source: DataSourceRef,
        field_path: str,
        raw_value: str | int | float | None = None,
    ) -> FieldRef:
        raw = str(raw_value) if raw_value is not None else None
        return cls(file_path=source.file_path, field_path=field_path, raw_value=raw)


def source_from_document(
    file_path: Path,
    document: dict,
) -> DataSourceRef:
    """Cria DataSourceRef a partir de um documento YAML carregado."""
    metadata = document.get("metadata") or {}
    return DataSourceRef(
        file_path=str(file_path),
        resource_kind=str(document.get("kind", "Unknown")),
        resource_name=str(metadata.get("name", file_path.stem)),
        namespace=metadata.get("namespace"),
    )
