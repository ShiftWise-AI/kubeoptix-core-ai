"""Descoberta centralizada de artefatos em apps/<app_group>/."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

IGNORED_APP_DIRS = frozenset({"__sem_app__"})

# Subdiretórios conhecidos sob apps/<app>/ → categoria de recurso
APPS_SUBDIR_CATEGORIES: dict[str, str] = {
    "deployments": "workload",
    "statefulsets": "workload",
    "daemonsets": "workload",
    "deploymentconfigs": "workload",
    "jobs": "workload",
    "cronjobs": "workload",
    "replicationcontrollers": "workload",
    "replicasets": "workload",
    "pods": "pod",
    "pods.metrics.k8s.io": "pod_metrics",
    "pod-metrics": "pod_metrics",
    "persistentvolumeclaims": "pvc",
    "pvc": "pvc",
    "secrets": "secret",
    "services": "service",
    "routes": "route",
    "configmaps": "configmap",
    "hpa": "hpa",
    "vpa": "vpa",
    "pdb": "pdb",
}

# kind YAML → categoria (fallback para arquivos fora de subdir conhecido)
KIND_TO_CATEGORY: dict[str, str] = {
    "Deployment": "workload",
    "StatefulSet": "workload",
    "DaemonSet": "workload",
    "DeploymentConfig": "workload",
    "Job": "workload",
    "CronJob": "workload",
    "ReplicationController": "workload",
    "ReplicaSet": "workload",
    "Pod": "pod",
    "Service": "service",
    "Route": "route",
    "ConfigMap": "configmap",
    "Secret": "secret",
    "PersistentVolumeClaim": "pvc",
    "HorizontalPodAutoscaler": "hpa",
    "VerticalPodAutoscaler": "vpa",
    "PodDisruptionBudget": "pdb",
}


def _peek_yaml_kind(file_path: Path) -> str | None:
    """Lê apenas o campo kind do YAML sem parser completo."""
    try:
        import yaml

        text = file_path.read_text(encoding="utf-8")
        document = yaml.safe_load(text)
        if isinstance(document, dict):
            kind = document.get("kind")
            if kind is not None:
                return str(kind)
    except Exception:
        return None
    return None


def _category_for_apps_file(app_dir: Path, file_path: Path) -> str | None:
    rel = file_path.relative_to(app_dir)
    parts = rel.parts

    if file_path.suffix.lower() == ".log":
        return "pod_log" if parts[0] == "pod-logs" else None

    if file_path.suffix.lower() not in (".yaml", ".yml"):
        return None

    if len(parts) == 1:
        kind = _peek_yaml_kind(file_path)
        return KIND_TO_CATEGORY.get(kind) if kind else None

    subdir = parts[0]
    if subdir in APPS_SUBDIR_CATEGORIES:
        return APPS_SUBDIR_CATEGORIES[subdir]

    kind = _peek_yaml_kind(file_path)
    return KIND_TO_CATEGORY.get(kind) if kind else None


def discover_apps_tree(namespace_root: Path) -> dict[str, tuple[Path, ...]]:
    """
    Varre recursivamente apps/<app_group>/ e classifica arquivos por categoria.

    Retorna dict categoria → tupla de paths (ordenados, sem duplicatas).
    """
    grouped: dict[str, list[Path]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)

    apps_dir = namespace_root / "apps"
    if not apps_dir.is_dir():
        return {}

    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir() or app_dir.name in IGNORED_APP_DIRS:
            continue

        for file_path in sorted(app_dir.rglob("*")):
            if not file_path.is_file():
                continue

            category = _category_for_apps_file(app_dir, file_path)
            if category is None:
                continue

            dedupe_key = f"{app_dir.name}/{file_path.name}"
            if dedupe_key in seen[category]:
                continue
            seen[category].add(dedupe_key)
            grouped[category].append(file_path)

    return {cat: tuple(paths) for cat, paths in grouped.items()}


def merge_file_lists(*lists: tuple[Path, ...]) -> tuple[Path, ...]:
    """Une listas de paths removendo duplicatas por caminho absoluto (mantém ordem)."""
    seen: set[str] = set()
    merged: list[Path] = []
    for file_list in lists:
        for path in file_list:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            merged.append(path)
    return tuple(merged)


def dedupe_yaml_by_stem(
    paths: tuple[Path, ...],
    *,
    prefer_resources: bool = True,
) -> tuple[Path, ...]:
    """
    Remove YAML duplicados pelo nome do recurso (stem do arquivo).

    Quando o mesmo recurso existe em `resources/` e `apps/`, mantém `resources/`.
    """
    by_stem: dict[str, Path] = {}
    order: list[str] = []

    for path in paths:
        stem = path.stem
        if stem not in by_stem:
            order.append(stem)
            by_stem[stem] = path
            continue

        existing = by_stem[stem]
        if not prefer_resources:
            continue

        existing_is_resource = "/resources/" in str(existing)
        current_is_resource = "/resources/" in str(path)
        if current_is_resource and not existing_is_resource:
            by_stem[stem] = path

    return tuple(by_stem[stem] for stem in order)
