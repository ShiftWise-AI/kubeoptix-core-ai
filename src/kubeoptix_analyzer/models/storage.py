"""Modelos de storage (volumes e PVCs)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kubeoptix_analyzer.models.quantities import ResourceQuantity
from kubeoptix_analyzer.models.source import DataSourceRef, FieldRef


class VolumeMountSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    mount_path: str | None = None
    read_only: bool | None = None
    container_name: str | None = None
    source: FieldRef


class VolumeSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    volume_type: str
    claim_name: str | None = None
    source: FieldRef


class PersistentVolumeClaimSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    namespace: str
    storage_class: str | None = None
    access_modes: tuple[str, ...] = ()
    storage_request: ResourceQuantity | None = None
    source: DataSourceRef
