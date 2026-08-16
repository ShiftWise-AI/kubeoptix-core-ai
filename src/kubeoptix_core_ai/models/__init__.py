"""Modelos de dados normalizados."""

from kubeoptix_core_ai.models.metrics import ContainerMetrics, PodMetricsSnapshot
from kubeoptix_core_ai.models.node import NodeCondition, WorkNode
from kubeoptix_core_ai.models.quantities import ResourceQuantity
from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef
from kubeoptix_core_ai.models.workload import (
    ContainerSpec,
    HPASpec,
    NamespaceWorkloadBundle,
    ProbeSpec,
    Workload,
)

__all__ = [
    "ContainerMetrics",
    "ContainerSpec",
    "DataSourceRef",
    "FieldRef",
    "HPASpec",
    "NamespaceWorkloadBundle",
    "NodeCondition",
    "PodMetricsSnapshot",
    "ProbeSpec",
    "ResourceQuantity",
    "WorkNode",
    "Workload",
]
