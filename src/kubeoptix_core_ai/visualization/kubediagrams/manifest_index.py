"""Índice de manifests YAML do namespace para seleção de diagramas."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kubeoptix_core_ai.discovery.apps import merge_file_lists
from kubeoptix_core_ai.discovery.scanner import discover_namespace
from kubeoptix_core_ai.visualization.kubediagrams.manifests import (
    _is_architecture_workload,
    _platform_route_files,
    select_architecture_manifests,
)


def _resource_bucket(path: Path) -> str | None:
    """Classifica um arquivo YAML em bucket de recurso K8s/OpenShift."""
    text = str(path)
    if "/deployments/" in text or "/deployments.apps/" in text or "/deploymentconfigs/" in text:
        return "workload"
    if "/statefulsets/" in text or "/statefulsets.apps/" in text:
        return "workload"
    if "/daemonsets/" in text or "/daemonsets.apps/" in text:
        return "workload"
    if "/services/" in text:
        return "service"
    if "/routes/" in text or "/routes.route.openshift.io/" in text:
        return "route"
    if "/secrets/" in text:
        return "secret"
    if "/configmaps/" in text:
        return "configmap"
    if "/persistentvolumeclaims/" in text or "/pvc/" in text:
        return "pvc"
    if "/hpa/" in text or "/horizontalpodautoscalers.autoscaling/" in text:
        return "hpa"
    if "/pods/" in text or "/pods.metrics.k8s.io/" in text:
        return "pod"
    if "/verticalpodautoscalers" in text or "/vpa/" in text:
        return "vpa"
    if "/poddisruptionbudgets" in text or "/pdb/" in text:
        return "pdb"
    return None


def _prefer_path(existing: Path, candidate: Path) -> Path:
    """``resources/`` tem precedência sobre ``apps/`` para o mesmo recurso."""
    if "/resources/" in str(candidate) and "/resources/" not in str(existing):
        return candidate
    return existing


_BUCKET_ATTR: dict[str, str] = {
    "workload": "workloads",
    "service": "services",
    "route": "routes",
    "secret": "secrets",
    "configmap": "configmaps",
    "pvc": "pvcs",
    "hpa": "hpas",
    "pod": "pods",
    "node": "nodes",
}


@dataclass
class ManifestIndex:
    """Mapa nome de recurso → arquivo YAML por categoria."""

    namespace_root: Path
    workloads: dict[str, Path] = field(default_factory=dict)
    services: dict[str, Path] = field(default_factory=dict)
    routes: dict[str, Path] = field(default_factory=dict)
    secrets: dict[str, Path] = field(default_factory=dict)
    configmaps: dict[str, Path] = field(default_factory=dict)
    pvcs: dict[str, Path] = field(default_factory=dict)
    hpas: dict[str, Path] = field(default_factory=dict)
    pods: dict[str, Path] = field(default_factory=dict)
    nodes: dict[str, Path] = field(default_factory=dict)

    def _register(self, bucket: str, name: str, path: Path) -> None:
        table: dict[str, Path]
        match bucket:
            case "workload":
                table = self.workloads
            case "service":
                table = self.services
            case "route":
                table = self.routes
            case "secret":
                table = self.secrets
            case "configmap":
                table = self.configmaps
            case "pvc":
                table = self.pvcs
            case "hpa":
                table = self.hpas
            case "pod":
                table = self.pods
            case "node":
                table = self.nodes
            case _:
                return
        if name in table:
            table[name] = _prefer_path(table[name], path)
        else:
            table[name] = path

    def path_for(self, bucket: str, name: str) -> Path | None:
        attr = _BUCKET_ATTR.get(bucket)
        if attr is None:
            return None
        table: dict[str, Path] = getattr(self, attr)
        return table.get(name)

    def relative_sources(self, paths: tuple[Path, ...]) -> tuple[str, ...]:
        root = self.namespace_root.resolve()
        sources: list[str] = []
        for path in paths:
            try:
                sources.append(str(path.resolve().relative_to(root)))
            except ValueError:
                sources.append(path.name)
        return tuple(sources)


def build_manifest_index(namespace_root: Path, *, worknodes_path: Path | None = None) -> ManifestIndex:
    """Constrói índice a partir do inventário descoberto no namespace."""
    index = ManifestIndex(namespace_root=namespace_root)
    if not namespace_root.is_dir():
        return index

    paths = discover_namespace(namespace_root)
    candidates = merge_file_lists(
        paths.workload_files,
        paths.service_files,
        paths.route_files,
        paths.secret_files,
        paths.configmap_files,
        paths.pvc_files,
        paths.hpa_files,
        paths.vpa_files,
        paths.pdb_files,
        paths.pod_files,
        _platform_route_files(namespace_root),
    )

    for path in candidates:
        bucket = _resource_bucket(path)
        if bucket is None:
            continue
        index._register(bucket, path.stem, path)

    if worknodes_path is not None and worknodes_path.is_dir():
        for node_file in sorted(worknodes_path.glob("*.yaml")):
            index._register("node", node_file.stem, node_file)

    return index


def collect_paths(index: ManifestIndex, *lookups: tuple[str, str]) -> tuple[Path, ...]:
    """Resolve tuplas ``(bucket, name)`` em paths únicos preservando ordem."""
    seen: set[str] = set()
    result: list[Path] = []
    for bucket, name in lookups:
        path = index.path_for(bucket, name)
        if path is None:
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return tuple(result)


def merge_manifest_paths(*groups: tuple[Path, ...]) -> tuple[Path, ...]:
    return merge_file_lists(*groups)
