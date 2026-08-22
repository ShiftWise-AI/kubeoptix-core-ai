"""Modelos de worknode normalizados."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from kubeoptix_core_ai.models.quantities import ResourceQuantity
from kubeoptix_core_ai.models.source import DataSourceRef


class NodeCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    status: str
    reason: str | None = None
    message: str | None = None


class WorkNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    labels: dict[str, str] = Field(default_factory=dict)
    datacenter: str | None = None
    role: str | None = None
    env: str | None = None
    architecture: str | None = None
    cpu_capacity: ResourceQuantity | None = None
    cpu_allocatable: ResourceQuantity | None = None
    memory_capacity: ResourceQuantity | None = None
    memory_allocatable: ResourceQuantity | None = None
    max_pods: int | None = None
    conditions: tuple[NodeCondition, ...] = ()
    taints: tuple[dict, ...] = ()
    ready: bool | None = None
    kubelet_version: str | None = None
    os_image: str | None = None
    container_runtime: str | None = None
    mco_state: str | None = None
    mco_current_config: str | None = None
    mco_desired_config: str | None = None
    source: DataSourceRef

    @property
    def mco_synced(self) -> bool | None:
        if not self.mco_current_config or not self.mco_desired_config:
            return None
        return self.mco_current_config == self.mco_desired_config


class WorkNodeBundle(BaseModel):
    """Resultado do carregamento de worknodes."""

    nodes: tuple[WorkNode, ...]
    parse_errors: tuple[str, ...] = ()

    @property
    def node_count(self) -> int:
        return len(self.nodes)
