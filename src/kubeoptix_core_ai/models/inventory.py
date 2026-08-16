"""Modelos de inventário de namespace (Services, Routes, ConfigMaps, logs, operadores)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from kubeoptix_core_ai.models.source import DataSourceRef


class ServicePortSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    port: int | None = None
    target_port: int | str | None = None
    protocol: str | None = None


class ServiceSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    namespace: str
    service_type: str | None = None
    cluster_ip: str | None = None
    selector: dict[str, str] = Field(default_factory=dict)
    ports: tuple[ServicePortSpec, ...] = ()
    session_affinity: str | None = None
    source: DataSourceRef


class RouteSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    namespace: str
    host: str | None = None
    target_service: str | None = None
    target_port: int | str | None = None
    tls_termination: str | None = None
    tls_insecure_policy: str | None = None
    wildcard_policy: str | None = None
    router_name: str | None = None
    router_canonical_hostname: str | None = None
    source: DataSourceRef


class ConfigMapSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    namespace: str
    app_group: str | None = None
    keys: tuple[str, ...] = ()
    source: DataSourceRef


class SecretReference(BaseModel):
    """Referência a Secret inferida de Deployments (sem conteúdo)."""

    model_config = ConfigDict(frozen=True)

    name: str
    usage: str  # envFrom | volume | imagePullSecrets
    workload: str
    source: DataSourceRef


class PodLogSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_group: str
    pod_name: str
    file_path: str
    line_count: int
    levels: dict[str, int] = Field(default_factory=dict)
    empty: bool = False
    runtime_signals: tuple[str, ...] = ()


class OperatorCSVSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    display_name: str | None = None
    version: str | None = None
    provider: str | None = None
    phase: str | None = None
    reason: str | None = None
    package_name: str | None = None
    default_channel: str | None = None
    channel_current_csv: str | None = None
    upgrade_status: str | None = None  # AtLatestKnown | UpgradeAvailable | Unknown
    source: DataSourceRef
