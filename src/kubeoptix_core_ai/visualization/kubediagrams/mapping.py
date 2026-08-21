"""Mapeamento de tipos de diagrama → manifests YAML (de/para)."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from kubeoptix_core_ai.models.inventory import RouteSpec, ServiceSpec
from kubeoptix_core_ai.models.workload import Workload

if TYPE_CHECKING:
    from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.kubediagrams.manifest_index import (
    ManifestIndex,
    build_manifest_index,
    collect_paths,
    merge_manifest_paths,
)
from kubeoptix_core_ai.visualization.kubediagrams.manifests import select_architecture_manifests
from kubeoptix_core_ai.visualization.topology.matcher import services_for_workload, workloads_for_service


class DiagramKind(str, Enum):
    """Tipos de diagrama suportados pelo relatório."""

    NAMESPACE_ARCHITECTURE = "namespace_architecture"
    WORKLOAD = "workload"
    EXTERNAL_COMMUNICATION = "external_communication"
    INTERNAL_COMMUNICATION = "internal_communication"
    EXTERNAL_DEPENDENCIES = "external_dependencies"
    WORKLOAD_NODE_PLACEMENT = "workload_node_placement"


# De/para documentado: tipo de diagrama → objetos YAML incluídos.
DIAGRAM_YAML_MAPPING: dict[DiagramKind, tuple[str, ...]] = {
    DiagramKind.NAMESPACE_ARCHITECTURE: (
        "Deployment | StatefulSet | DaemonSet | DeploymentConfig | Job | CronJob | ReplicationController | ReplicaSet (standalone)",
        "Pod (agrupados por workload, com contagem de réplicas)",
        "HPA | VPA | PDB",
        "Service | Route | Ingress | NetworkPolicy",
        "PersistentVolume | PersistentVolumeClaim | StorageClass",
        "ConfigMap | Secret | ServiceAccount",
    ),
    DiagramKind.WORKLOAD: (
        "Deployment (workloads do grupo)",
        "Service (associados por selector)",
        "Secret | ConfigMap | PVC | HPA (referenciados)",
    ),
    DiagramKind.EXTERNAL_COMMUNICATION: (
        "Route",
        "Service (spec.to.name)",
        "Deployment (pods selecionados pelo Service)",
    ),
    DiagramKind.INTERNAL_COMMUNICATION: (
        "Service",
        "Deployment (pods selecionados pelo Service)",
    ),
    DiagramKind.EXTERNAL_DEPENDENCIES: (
        "Deployment",
        "Secret (imagePullSecrets / envFrom)",
        "ConfigMap (referenciados)",
        "PVC (volumes)",
    ),
    DiagramKind.WORKLOAD_NODE_PLACEMENT: (
        "Pod (spec.nodeName)",
        "Node (worknodes/)",
    ),
}


def manifest_index_for(bundle: AssessmentBundle) -> ManifestIndex:
    namespace_root = bundle.config.namespace_path(bundle.analysis.namespace)
    return build_manifest_index(namespace_root, worknodes_path=bundle.config.worknodes_path)


def manifests_for_namespace_architecture(
    bundle: AssessmentBundle,
    index: ManifestIndex | None = None,
) -> tuple:
    namespace_root = bundle.config.namespace_path(bundle.analysis.namespace)
    return select_architecture_manifests(namespace_root)


def manifests_for_external_route(
    route: RouteSpec,
    bundle: AssessmentBundle,
    index: ManifestIndex | None = None,
) -> tuple:
    idx = index or manifest_index_for(bundle)
    lookups: list[tuple[str, str]] = [("route", route.name)]
    if route.target_service:
        lookups.append(("service", route.target_service))
        service = next((s for s in bundle.context.services if s.name == route.target_service), None)
        if service is not None:
            for wl in workloads_for_service(service, bundle.context.workloads):
                lookups.append(("workload", wl.name))
    return collect_paths(idx, *lookups)


def manifests_for_internal_service(
    service: ServiceSpec,
    bundle: AssessmentBundle,
    index: ManifestIndex | None = None,
) -> tuple:
    idx = index or manifest_index_for(bundle)
    lookups: list[tuple[str, str]] = [("service", service.name)]
    for wl in workloads_for_service(service, bundle.context.workloads):
        lookups.append(("workload", wl.name))
    return collect_paths(idx, *lookups)


def manifests_for_workload_dependencies(
    workload: Workload,
    bundle: AssessmentBundle,
    index: ManifestIndex | None = None,
) -> tuple:
    idx = index or manifest_index_for(bundle)
    lookups: list[tuple[str, str]] = [("workload", workload.name)]
    for secret_name in workload.referenced_secrets:
        lookups.append(("secret", secret_name))
    for cm_name in workload.referenced_configmaps:
        lookups.append(("configmap", cm_name))
    for vol in workload.volumes:
        if vol.claim_name:
            lookups.append(("pvc", vol.claim_name))
    if workload.hpa is not None:
        lookups.append(("hpa", workload.hpa.name))
    return collect_paths(idx, *lookups)


def manifests_for_proposed_namespace(
    workloads: tuple[Workload, ...],
    bundle: AssessmentBundle,
    index: ManifestIndex | None = None,
) -> tuple:
    """Manifests do recorte proposto: workloads, Services, Routes e dependências."""
    idx = index or manifest_index_for(bundle)
    paths = manifests_for_workload_group(workloads, bundle, idx)
    service_names = {
        svc.name
        for wl in workloads
        for svc in services_for_workload(wl, bundle.context.services)
    }
    lookups: list[tuple[str, str]] = []
    for route in bundle.context.routes:
        if route.target_service and route.target_service in service_names:
            lookups.append(("route", route.name))
    for wl in workloads:
        for pod_name in idx.pods:
            if pod_name == wl.name or pod_name.startswith(f"{wl.name}-"):
                lookups.append(("pod", pod_name))
    return merge_manifest_paths(paths, collect_paths(idx, *lookups))


def manifests_for_workload_group(
    workloads: tuple[Workload, ...],
    bundle: AssessmentBundle,
    index: ManifestIndex | None = None,
) -> tuple:
    idx = index or manifest_index_for(bundle)
    lookups: list[tuple[str, str]] = []
    service_names: set[str] = set()
    for wl in workloads:
        lookups.append(("workload", wl.name))
        for secret_name in wl.referenced_secrets:
            lookups.append(("secret", secret_name))
        for cm_name in wl.referenced_configmaps:
            lookups.append(("configmap", cm_name))
        for vol in wl.volumes:
            if vol.claim_name:
                lookups.append(("pvc", vol.claim_name))
        if wl.hpa is not None:
            lookups.append(("hpa", wl.hpa.name))
        for svc in services_for_workload(wl, bundle.context.services):
            if svc.name not in service_names:
                service_names.add(svc.name)
                lookups.append(("service", svc.name))
    return collect_paths(idx, *lookups)


def manifests_for_workload_node_placement(
    bundle: AssessmentBundle,
    index: ManifestIndex | None = None,
) -> tuple:
    idx = index or manifest_index_for(bundle)
    lookups: list[tuple[str, str]] = []
    node_names: set[str] = set()
    for wl in bundle.context.workloads:
        lookups.append(("workload", wl.name))
        for placement in wl.placements:
            if placement.node_name and placement.node_name not in node_names:
                node_names.add(placement.node_name)
                lookups.append(("node", placement.node_name))
            if placement.pod_name:
                lookups.append(("pod", placement.pod_name))
    return collect_paths(idx, *lookups)
