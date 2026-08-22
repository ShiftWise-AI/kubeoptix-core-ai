"""Modelos de workload normalizados."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from kubeoptix_core_ai.models.metrics import PodMetricsSnapshot
from kubeoptix_core_ai.models.inventory import (
    ConfigMapSpec,
    EventSpec,
    OperatorCSVSpec,
    PodLogSummary,
    RouteSpec,
    SecretReference,
    ServiceSpec,
)
from kubeoptix_core_ai.models.quantities import ResourceQuantity
from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef
from kubeoptix_core_ai.models.storage import (
    PersistentVolumeClaimSpec,
    VolumeMountSpec,
    VolumeSpec,
)


class ProbeSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    probe_type: str  # readinessProbe | livenessProbe | startupProbe
    handler_type: str | None = None  # httpGet | tcpSocket | exec
    path: str | None = None
    port: int | str | None = None
    source: FieldRef


class ContainerSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    image: str | None = None
    cpu_request: ResourceQuantity | None = None
    cpu_limit: ResourceQuantity | None = None
    memory_request: ResourceQuantity | None = None
    memory_limit: ResourceQuantity | None = None
    readiness_probe: ProbeSpec | None = None
    liveness_probe: ProbeSpec | None = None
    startup_probe: ProbeSpec | None = None
    source: DataSourceRef


class HPASpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    min_replicas: int | None = None
    max_replicas: int | None = None
    target_workload_name: str | None = None
    target_workload_kind: str | None = None
    metrics: list[str] = Field(default_factory=list)
    source: DataSourceRef


class VPASpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    target_workload_name: str | None = None
    target_workload_kind: str | None = None
    update_mode: str | None = None
    source: DataSourceRef


class PDBSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    min_available: str | int | None = None
    max_unavailable: str | int | None = None
    selector: dict[str, str] = Field(default_factory=dict)
    source: DataSourceRef


class PodPlacement(BaseModel):
    model_config = ConfigDict(frozen=True)

    pod_name: str
    workload_name: str | None = None
    namespace: str
    node_name: str | None = None
    qos_class: str | None = None
    source: DataSourceRef


class Workload(BaseModel):
    model_config = ConfigDict(frozen=True)

    namespace: str
    name: str
    app_group: str
    kind: str
    replicas_desired: int | None = None
    replicas_ready: int | None = None
    replicas_available: int | None = None
    containers: tuple[ContainerSpec, ...] = ()
    node_selector: dict[str, str] = Field(default_factory=dict)
    affinity: dict | None = None
    tolerations: list[dict] | None = None
    topology_spread_constraints: list[dict] | None = None
    qos_class: str | None = None
    hpa: HPASpec | None = None
    vpa: VPASpec | None = None
    pdb: PDBSpec | None = None
    update_strategy: str | None = None
    schedule: str | None = None
    parent_cronjob: str | None = None
    placements: tuple[PodPlacement, ...] = ()
    metrics: tuple[PodMetricsSnapshot, ...] = ()
    volumes: tuple[VolumeSpec, ...] = ()
    volume_mounts: tuple[VolumeMountSpec, ...] = ()
    referenced_configmaps: tuple[str, ...] = ()
    referenced_secrets: tuple[str, ...] = ()
    image_pull_secrets: tuple[str, ...] = ()
    pod_template_labels: dict[str, str] = Field(default_factory=dict)
    match_labels: dict[str, str] = Field(default_factory=dict)
    total_cpu_request_per_pod_millicores: float | None = None
    total_memory_request_per_pod_bytes: float | None = None
    source: DataSourceRef


class NamespaceWorkloadBundle(BaseModel):
    """Resultado do carregamento de um namespace."""

    namespace: str
    workloads: tuple[Workload, ...]
    parse_errors: tuple[str, ...] = ()
    skipped_files: tuple[str, ...] = ()
    processed_files: tuple[str, ...] = ()
    pvcs: tuple[PersistentVolumeClaimSpec, ...] = ()
    services: tuple[ServiceSpec, ...] = ()
    routes: tuple[RouteSpec, ...] = ()
    configmaps: tuple[ConfigMapSpec, ...] = ()
    operators: tuple[OperatorCSVSpec, ...] = ()
    events: tuple[EventSpec, ...] = ()
    pod_logs: tuple[PodLogSummary, ...] = ()
    secret_references: tuple[SecretReference, ...] = ()

    @property
    def workload_count(self) -> int:
        return len(self.workloads)
