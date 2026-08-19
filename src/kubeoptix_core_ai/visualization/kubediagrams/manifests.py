"""Seleção de manifests YAML para diagramas KubeDiagrams."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.discovery.apps import merge_file_lists
from kubeoptix_core_ai.discovery.scanner import discover_namespace

# Controllers de workload canônicos (exclui ReplicaSet histórico e batch jobs).
_ARCHITECTURE_WORKLOAD_SUBDIRS = frozenset(
    {
        "deployments",
        "statefulsets",
        "daemonsets",
        "deploymentconfigs",
    }
)

_ARCHITECTURE_RESOURCE_DIRS = frozenset(
    {
        "deployments.apps",
        "statefulsets.apps",
        "daemonsets.apps",
        "deploymentconfigs.apps.openshift.io",
    }
)


def _is_architecture_workload(path: Path) -> bool:
    parts = path.parts
    if "apps" in parts:
        try:
            apps_idx = parts.index("apps")
            if apps_idx + 2 < len(parts):
                return parts[apps_idx + 2] in _ARCHITECTURE_WORKLOAD_SUBDIRS
        except ValueError:
            return False
    if "resources" in parts:
        try:
            resources_idx = parts.index("resources")
            if resources_idx + 1 < len(parts):
                return parts[resources_idx + 1] in _ARCHITECTURE_RESOURCE_DIRS
        except ValueError:
            return False
    return False


def _platform_route_files(namespace_root: Path) -> tuple[Path, ...]:
    """Routes em ``apps/__sem_app__/routes`` (plataforma OpenShift)."""
    routes_dir = namespace_root / "apps" / "__sem_app__" / "routes"
    if not routes_dir.is_dir():
        return ()
    return tuple(sorted(routes_dir.glob("*.yaml")))


def select_architecture_manifests(namespace_root: Path) -> tuple[Path, ...]:
    """
    Seleciona YAMLs para o diagrama de arquitetura do namespace.

    Inclui controllers de workload, Services e Routes (incluindo ``__sem_app__``).
    Exclui ReplicaSets, métricas, operadores OLM e logs.
    """
    if not namespace_root.is_dir():
        return ()

    paths = discover_namespace(namespace_root)
    workload_files = tuple(path for path in paths.workload_files if _is_architecture_workload(path))

    return merge_file_lists(
        workload_files,
        paths.service_files,
        paths.route_files,
        _platform_route_files(namespace_root),
    )
