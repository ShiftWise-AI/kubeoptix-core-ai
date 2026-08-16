"""Modelos de métricas de runtime (PodMetrics)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kubeoptix_core_ai.models.quantities import ResourceQuantity
from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef


class ContainerMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    container_name: str
    cpu_usage: ResourceQuantity | None = None
    memory_usage: ResourceQuantity | None = None


class PodMetricsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    pod_name: str
    namespace: str
    containers: tuple[ContainerMetrics, ...] = ()
    timestamp: str | None = None
    window_seconds: float | None = None
    source: DataSourceRef
