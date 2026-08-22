"""Descoberta de arquivos nos diretórios de dados."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kubeoptix_core_ai.discovery.apps import (
    IGNORED_APP_DIRS,
    dedupe_yaml_by_stem,
    discover_apps_tree,
    merge_file_lists,
)

IGNORED_RESOURCE_PREFIXES = (
    "packagemanifests.packages.operators.coreos.com",
    "clusterserviceversions.operators.coreos.com",
)

# Mapeamento apps/<app>/<subdir> → kind Kubernetes
WORKLOAD_APP_SUBDIRS: dict[str, str] = {
    "deployments": "Deployment",
    "statefulsets": "StatefulSet",
    "daemonsets": "DaemonSet",
    "deploymentconfigs": "DeploymentConfig",
    "jobs": "Job",
    "cronjobs": "CronJob",
    "replicationcontrollers": "ReplicationController",
    "replicasets": "ReplicaSet",
}

# Mapeamento resources/<api-resource-dir> → kind Kubernetes
WORKLOAD_RESOURCE_DIRS: dict[str, str] = {
    "deployments.apps": "Deployment",
    "statefulsets.apps": "StatefulSet",
    "daemonsets.apps": "DaemonSet",
    "deploymentconfigs.apps.openshift.io": "DeploymentConfig",
    "jobs.batch": "Job",
    "cronjobs.batch": "CronJob",
    "replicationcontrollers": "ReplicationController",
    "replicasets.apps": "ReplicaSet",
    "horizontalpodautoscalers.autoscaling": "HorizontalPodAutoscaler",
    "verticalpodautoscalers.autoscaling.k8s.io": "VerticalPodAutoscaler",
    "poddisruptionbudgets.policy": "PodDisruptionBudget",
    "secrets": "Secret",
    "configmaps": "ConfigMap",
}

AUTOSCALER_APP_SUBDIRS = frozenset({"hpa", "vpa", "pdb"})


@dataclass(frozen=True)
class NamespacePaths:
    """Caminhos relevantes descobertos em um namespace."""

    namespace: str
    root: Path
    workload_files: tuple[Path, ...]
    pod_files: tuple[Path, ...]
    pod_metrics_files: tuple[Path, ...]
    hpa_files: tuple[Path, ...]
    vpa_files: tuple[Path, ...] = ()
    pdb_files: tuple[Path, ...] = ()
    secret_files: tuple[Path, ...] = ()
    service_files: tuple[Path, ...] = ()
    route_files: tuple[Path, ...] = ()
    configmap_files: tuple[Path, ...] = ()
    pvc_files: tuple[Path, ...] = ()
    csv_files: tuple[Path, ...] = ()
    packagemanifest_files: tuple[Path, ...] = ()
    event_files: tuple[Path, ...] = ()
    pod_log_files: tuple[Path, ...] = ()

    @property
    def deployment_files(self) -> tuple[Path, ...]:
        """Compatibilidade: retorna apenas arquivos de Deployment."""
        return tuple(
            f for f in self.workload_files
            if f.parent.name == "deployments"
            or "deployments.apps" in f.parts
        )

    @property
    def processable_file_count(self) -> int:
        """Quantidade de arquivos que o loader de workloads itera."""
        return (
            len(self.workload_files)
            + len(self.pod_files)
            + len(self.pod_metrics_files)
            + len(self.hpa_files)
            + len(self.vpa_files)
            + len(self.pdb_files)
            + len(self.pvc_files)
            + len(self.service_files)
            + len(self.route_files)
            + len(self.configmap_files)
            + len(self.csv_files)
            + len(self.packagemanifest_files)
            + len(self.event_files)
            + len(self.pod_log_files)
        )


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


def _collect_workload_files(namespace_root: Path) -> tuple[Path, ...]:
    """Coleta controllers de workload; `resources/` tem precedência sobre `apps/`."""
    by_stem: dict[str, Path] = {}
    order: list[str] = []

    def _register(path: Path) -> None:
        if path.stem not in by_stem:
            order.append(path.stem)
            by_stem[path.stem] = path
            return
        existing = by_stem[path.stem]
        if "/resources/" in str(path) and "/resources/" not in str(existing):
            by_stem[path.stem] = path

    for subdir in WORKLOAD_APP_SUBDIRS:
        apps_dir = namespace_root / "apps"
        if apps_dir.is_dir():
            for app_dir in sorted(apps_dir.iterdir()):
                if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
                    continue
                target = app_dir / subdir
                if target.is_dir():
                    for path in sorted(target.glob("*.yaml")):
                        _register(path)

    for resource_dir in WORKLOAD_RESOURCE_DIRS:
        if resource_dir in (
            "horizontalpodautoscalers.autoscaling",
            "verticalpodautoscalers.autoscaling.k8s.io",
            "poddisruptionbudgets.policy",
            "secrets",
            "configmaps",
        ):
            continue
        res_path = namespace_root / "resources" / resource_dir
        if res_path.is_dir():
            for path in sorted(res_path.glob("*.yaml")):
                _register(path)

    return tuple(by_stem[stem] for stem in order)


def _collect_autoscaler_files(
    namespace_root: Path,
    subdir: str,
    resource_dir: str,
) -> tuple[Path, ...]:
    files: list[Path] = []
    apps_dir = namespace_root / "apps"
    if apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
                continue
            target = app_dir / subdir
            if target.is_dir():
                files.extend(sorted(target.glob("*.yaml")))
    res_path = namespace_root / "resources" / resource_dir
    if res_path.is_dir():
        files.extend(sorted(res_path.glob("*.yaml")))
    return tuple(files)


def discover_namespace(namespace_root: Path) -> NamespacePaths:
    """
    Descobre arquivos relevantes em um diretório de namespace.

    Fontes: `apps/<app_group>/` (varredura recursiva) e `resources/`.
    Workloads canônicos: Deployment, StatefulSet, DaemonSet, DeploymentConfig,
    Job, CronJob, ReplicationController (e ReplicaSet para correlação).
    """
    namespace = namespace_root.name
    apps_tree = discover_apps_tree(namespace_root)

    workload_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_workload_files(namespace_root),
            apps_tree.get("workload", ()),
        )
    )

    pod_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_pod_files(namespace_root),
            apps_tree.get("pod", ()),
        )
    )

    pod_metrics_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_pod_metrics_files(namespace_root),
            apps_tree.get("pod_metrics", ()),
        )
    )

    hpa_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_autoscaler_files(
                namespace_root, "hpa", "horizontalpodautoscalers.autoscaling"
            ),
            apps_tree.get("hpa", ()),
        )
    )
    vpa_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_autoscaler_files(
                namespace_root, "vpa", "verticalpodautoscalers.autoscaling.k8s.io"
            ),
            apps_tree.get("vpa", ()),
        )
    )
    pdb_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_autoscaler_files(
                namespace_root, "pdb", "poddisruptionbudgets.policy"
            ),
            apps_tree.get("pdb", ()),
        )
    )

    pod_log_files = merge_file_lists(
        _collect_pod_log_files(namespace_root),
        apps_tree.get("pod_log", ()),
    )

    secret_files = merge_file_lists(
        _collect_named_yaml_files(namespace_root, "secrets", "secrets"),
        apps_tree.get("secret", ()),
    )

    service_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_named_yaml_files(namespace_root, "services", "services"),
            apps_tree.get("service", ()),
        )
    )
    route_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_named_yaml_files(
                namespace_root, "routes.route.openshift.io", "routes"
            ),
            apps_tree.get("route", ()),
        )
    )
    configmap_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_named_yaml_files(namespace_root, "configmaps", "configmaps"),
            apps_tree.get("configmap", ()),
        )
    )

    pvc_files = dedupe_yaml_by_stem(
        merge_file_lists(
            _collect_pvc_files(namespace_root),
            apps_tree.get("pvc", ()),
        )
    )

    csv_dir = namespace_root / "resources" / "clusterserviceversions.operators.coreos.com"
    csv_files = tuple(sorted(csv_dir.glob("*.yaml"))) if csv_dir.is_dir() else ()

    pm_dir = namespace_root / "resources" / "packagemanifests.packages.operators.coreos.com"
    packagemanifest_files = (
        tuple(sorted(pm_dir.glob("*.yaml"))) if pm_dir.is_dir() else ()
    )

    event_files = _collect_event_files(namespace_root)

    return NamespacePaths(
        namespace=namespace,
        root=namespace_root,
        workload_files=workload_files,
        pod_files=pod_files,
        pod_metrics_files=pod_metrics_files,
        hpa_files=hpa_files,
        vpa_files=vpa_files,
        pdb_files=pdb_files,
        secret_files=secret_files,
        service_files=service_files,
        route_files=route_files,
        configmap_files=configmap_files,
        pvc_files=pvc_files,
        csv_files=csv_files,
        packagemanifest_files=packagemanifest_files,
        event_files=event_files,
        pod_log_files=pod_log_files,
    )


def _collect_pod_files(namespace_root: Path) -> tuple[Path, ...]:
    pod_dir = namespace_root / "resources" / "pods"
    return tuple(sorted(pod_dir.glob("*.yaml"))) if pod_dir.is_dir() else ()


def _collect_pod_metrics_files(namespace_root: Path) -> tuple[Path, ...]:
    metrics_dir = namespace_root / "resources" / "pods.metrics.k8s.io"
    return (
        tuple(sorted(metrics_dir.glob("*.yaml"))) if metrics_dir.is_dir() else ()
    )


def _collect_pvc_files(namespace_root: Path) -> tuple[Path, ...]:
    pvc_dir = namespace_root / "resources" / "persistentvolumeclaims"
    return tuple(sorted(pvc_dir.glob("*.yaml"))) if pvc_dir.is_dir() else ()


def _collect_event_files(namespace_root: Path) -> tuple[Path, ...]:
    """Coleta Events; `resources/events/` tem precedência sobre `events.events.k8s.io/`."""
    seen: dict[str, Path] = {}
    for subdir in ("events", "events.events.k8s.io"):
        event_dir = namespace_root / "resources" / subdir
        if not event_dir.is_dir():
            continue
        for path in sorted(event_dir.glob("*.yaml")):
            seen.setdefault(path.stem, path)
    return tuple(seen[stem] for stem in sorted(seen))


def _collect_pod_log_files(namespace_root: Path) -> tuple[Path, ...]:
    pod_log_files: list[Path] = []
    apps_dir = namespace_root / "apps"
    if apps_dir.is_dir():
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
                continue
            logs_dir = app_dir / "pod-logs"
            if logs_dir.is_dir():
                pod_log_files.extend(sorted(logs_dir.glob("*.log")))
    return tuple(sorted(pod_log_files))


def list_namespace_dirs(workloads_base: Path) -> list[Path]:
    """Lista diretórios de namespace (exclui worknodes)."""
    if not workloads_base.is_dir():
        return []
    return sorted(
        p
        for p in workloads_base.iterdir()
        if p.is_dir() and p.name != "worknodes"
    )
