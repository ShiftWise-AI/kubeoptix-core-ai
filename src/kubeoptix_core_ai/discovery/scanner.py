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
    csv_files: tuple[Path, ...] = ()
    packagemanifest_files: tuple[Path, ...] = ()
    pod_log_files: tuple[Path, ...] = ()

    @property
    def deployment_files(self) -> tuple[Path, ...]:
        """Compatibilidade: retorna apenas arquivos de Deployment."""
        return tuple(
            f for f in self.workload_files
            if f.parent.name == "deployments"
            or "deployments.apps" in f.parts
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
    """Coleta todos os controllers de workload de apps/ e resources/."""
    seen: dict[str, Path] = {}

    for subdir in WORKLOAD_APP_SUBDIRS:
        apps_dir = namespace_root / "apps"
        if apps_dir.is_dir():
            for app_dir in sorted(apps_dir.iterdir()):
                if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
                    continue
                target = app_dir / subdir
                if target.is_dir():
                    for path in sorted(target.glob("*.yaml")):
                        key = f"{subdir}/{path.stem}"
                        seen.setdefault(key, path)

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
                key = f"resources/{resource_dir}/{path.stem}"
                seen.setdefault(key, path)

    return tuple(seen.values())


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

    Workloads canônicos: Deployment, StatefulSet, DaemonSet, DeploymentConfig,
    Job, CronJob, ReplicationController (e ReplicaSet para correlação).
    """
    namespace = namespace_root.name
    workload_files = _collect_workload_files(namespace_root)

    pod_dir = namespace_root / "resources" / "pods"
    pod_files = tuple(sorted(pod_dir.glob("*.yaml"))) if pod_dir.is_dir() else ()

    metrics_dir = namespace_root / "resources" / "pods.metrics.k8s.io"
    pod_metrics_files = (
        tuple(sorted(metrics_dir.glob("*.yaml"))) if metrics_dir.is_dir() else ()
    )

    hpa_files = _collect_autoscaler_files(
        namespace_root, "hpa", "horizontalpodautoscalers.autoscaling"
    )
    vpa_files = _collect_autoscaler_files(
        namespace_root, "vpa", "verticalpodautoscalers.autoscaling.k8s.io"
    )
    pdb_files = _collect_autoscaler_files(
        namespace_root, "pdb", "poddisruptionbudgets.policy"
    )

    pod_log_files: list[Path] = []
    apps_dir = namespace_root / "apps"
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

    secret_files = _collect_named_yaml_files(namespace_root, "secrets", "secrets")

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
