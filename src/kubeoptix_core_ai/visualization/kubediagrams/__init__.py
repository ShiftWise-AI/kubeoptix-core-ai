"""Integração com KubeDiagrams para diagramas de arquitetura Kubernetes/OpenShift."""

from kubeoptix_core_ai.visualization.kubediagrams.manifest_index import (
    ManifestIndex,
    build_manifest_index,
)
from kubeoptix_core_ai.visualization.kubediagrams.mapping import (
    DIAGRAM_YAML_MAPPING,
    DiagramKind,
    manifest_index_for,
    manifests_for_external_route,
    manifests_for_internal_service,
    manifests_for_namespace_architecture,
    manifests_for_proposed_namespace,
    manifests_for_workload_dependencies,
    manifests_for_workload_group,
    manifests_for_workload_node_placement,
)
from kubeoptix_core_ai.visualization.kubediagrams.manifests import select_architecture_manifests
from kubeoptix_core_ai.visualization.kubediagrams.renderer import (
    KubeDiagramsRenderer,
    is_kubediagrams_available,
)

__all__ = [
    "DIAGRAM_YAML_MAPPING",
    "DiagramKind",
    "KubeDiagramsRenderer",
    "ManifestIndex",
    "build_manifest_index",
    "is_kubediagrams_available",
    "manifest_index_for",
    "manifests_for_external_route",
    "manifests_for_internal_service",
    "manifests_for_namespace_architecture",
    "manifests_for_proposed_namespace",
    "manifests_for_workload_dependencies",
    "manifests_for_workload_group",
    "manifests_for_workload_node_placement",
    "select_architecture_manifests",
]
