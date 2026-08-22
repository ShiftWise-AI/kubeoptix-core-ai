"""Contexto compartilhado para analisadores determinísticos."""

from __future__ import annotations

from dataclasses import dataclass

from kubeoptix_core_ai.models.node import WorkNode
from kubeoptix_core_ai.models.storage import PersistentVolumeClaimSpec
from kubeoptix_core_ai.models.workload import NamespaceWorkloadBundle, Workload


@dataclass(frozen=True)
class AnalysisContext:
    """Dados normalizados disponíveis para análise."""

    bundle: NamespaceWorkloadBundle
    nodes: tuple[WorkNode, ...]

    @property
    def namespace(self) -> str:
        return self.bundle.namespace

    @property
    def workloads(self) -> tuple[Workload, ...]:
        return self.bundle.workloads

    @property
    def pvcs(self) -> tuple[PersistentVolumeClaimSpec, ...]:
        return self.bundle.pvcs

    @property
    def has_runtime_metrics(self) -> bool:
        return any(w.metrics for w in self.workloads)

    @property
    def services(self):
        return self.bundle.services

    @property
    def routes(self):
        return self.bundle.routes

    @property
    def configmaps(self):
        return self.bundle.configmaps

    @property
    def operators(self):
        return self.bundle.operators

    @property
    def events(self):
        return self.bundle.events

    @property
    def pod_logs(self):
        return self.bundle.pod_logs

    @property
    def secret_references(self):
        return self.bundle.secret_references
