"""Descoberta de arquivos nos diretórios de dados."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Diretórios de ruído que não representam workloads do namespace
IGNORED_APP_DIRS = frozenset({"__sem_app__"})
IGNORED_RESOURCE_PREFIXES = (
    "packagemanifests.packages.operators.coreos.com",
    "clusterserviceversions.operators.coreos.com",
)


@dataclass(frozen=True)
class NamespacePaths:
    """Caminhos relevantes descobertos em um namespace."""

    namespace: str
    root: Path
    deployment_files: tuple[Path, ...]
    pod_files: tuple[Path, ...]
    pod_metrics_files: tuple[Path, ...]
    hpa_files: tuple[Path, ...]
    service_files: tuple[Path, ...] = ()
    route_files: tuple[Path, ...] = ()
    configmap_files: tuple[Path, ...] = ()
    csv_files: tuple[Path, ...] = ()
    packagemanifest_files: tuple[Path, ...] = ()
    pod_log_files: tuple[Path, ...] = ()


def _collect_named_yaml_files(
    namespace_root: Path,
    resources_subdir: str,
    apps_subdir: str,
) -> tuple[Path, ...]:
    """Coleta YAML por nome; `resources/` tem precedência sobre `apps/<app>/`."""
    seen: dict[str, Path] = {}
    res_dir = namespace_root / "resources" / resources_subdir
    if res_dir.is_dir():
        for path in sorted(res_dir.glob("*.yaml")):
            seen[path.stem] = path
    apps_dir = namespace_root / "apps"
    if apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
                continue
            sub = app_dir / apps_subdir
            if sub.is_dir():
                for path in sorted(sub.glob("*.yaml")):
                    seen.setdefault(path.stem, path)
    return tuple(seen.values())


def discover_namespace(namespace_root: Path) -> NamespacePaths:
    """
    Descobre arquivos relevantes em um diretório de namespace.

    Fonte canônica de Deployments: apps/<app>/deployments/*.yaml
    """
    namespace = namespace_root.name
    deployment_files: list[Path] = []

    apps_dir = namespace_root / "apps"
    if apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
                continue
            deployments_dir = app_dir / "deployments"
            if deployments_dir.is_dir():
                deployment_files.extend(sorted(deployments_dir.glob("*.yaml")))

    pod_dir = namespace_root / "resources" / "pods"
    pod_files = tuple(sorted(pod_dir.glob("*.yaml"))) if pod_dir.is_dir() else ()

    metrics_dir = namespace_root / "resources" / "pods.metrics.k8s.io"
    pod_metrics_files = (
        tuple(sorted(metrics_dir.glob("*.yaml"))) if metrics_dir.is_dir() else ()
    )

    hpa_files: list[Path] = []
    if apps_dir.is_dir():
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
                continue
            hpa_dir = app_dir / "hpa"
            if hpa_dir.is_dir():
                hpa_files.extend(sorted(hpa_dir.glob("*.yaml")))

    pod_log_files: list[Path] = []
    if apps_dir.is_dir():
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
                continue
            logs_dir = app_dir / "pod-logs"
            if logs_dir.is_dir():
                pod_log_files.extend(sorted(logs_dir.glob("*.log")))

    csv_dir = namespace_root / "resources" / "clusterserviceversions.operators.coreos.com"
    csv_files = tuple(sorted(csv_dir.glob("*.yaml"))) if csv_dir.is_dir() else ()

    pm_dir = namespace_root / "resources" / "packagemanifests.packages.operators.coreos.com"
    packagemanifest_files = (
        tuple(sorted(pm_dir.glob("*.yaml"))) if pm_dir.is_dir() else ()
    )

    return NamespacePaths(
        namespace=namespace,
        root=namespace_root,
        deployment_files=tuple(deployment_files),
        pod_files=pod_files,
        pod_metrics_files=pod_metrics_files,
        hpa_files=tuple(sorted(hpa_files)),
        service_files=_collect_named_yaml_files(namespace_root, "services", "services"),
        route_files=_collect_named_yaml_files(
            namespace_root, "routes.route.openshift.io", "routes"
        ),
        configmap_files=_collect_named_yaml_files(namespace_root, "configmaps", "configmaps"),
        csv_files=csv_files,
        packagemanifest_files=packagemanifest_files,
        pod_log_files=tuple(sorted(pod_log_files)),
    )


def list_namespace_dirs(workloads_base: Path) -> list[Path]:
    """Lista diretórios de namespace (exclui worknodes)."""
    if not workloads_base.is_dir():
        return []
    return sorted(
        p
        for p in workloads_base.iterdir()
        if p.is_dir() and p.name != "worknodes"
    )
