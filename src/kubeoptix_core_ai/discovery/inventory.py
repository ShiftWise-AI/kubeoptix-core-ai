"""Inventário completo de arquivos em um namespace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kubeoptix_core_ai.discovery.apps import IGNORED_APP_DIRS
from kubeoptix_core_ai.discovery.scanner import IGNORED_RESOURCE_PREFIXES

# Extensões consideradas na contagem de arquivos encontrados
COUNTED_EXTENSIONS = frozenset({".yaml", ".yml", ".log"})


@dataclass(frozen=True)
class IgnoredFile:
    file_path: str
    reason: str


@dataclass(frozen=True)
class NamespaceFileInventory:
    namespace: str
    root: str
    files_found: tuple[str, ...]
    files_to_process: tuple[str, ...]
    files_ignored: tuple[IgnoredFile, ...]

    @property
    def files_found_count(self) -> int:
        return len(self.files_found)

    @property
    def files_to_process_count(self) -> int:
        return len(self.files_to_process)

    @property
    def files_ignored_count(self) -> int:
        return len(self.files_ignored)


def _is_ignored_path(path: Path, namespace_root: Path) -> str | None:
    """Retorna motivo de ignorar ou None se o arquivo é elegível para inventário."""
    try:
        rel = path.relative_to(namespace_root)
    except ValueError:
        return "fora do namespace"

    parts = rel.parts
    if not parts:
        return "caminho vazio"

    if parts[0] == "apps" and len(parts) >= 2 and parts[1] in IGNORED_APP_DIRS:
        return "diretório __sem_app__ (recursos de plataforma)"

    if parts[0] == "resources" and len(parts) >= 2:
        resource_type = parts[1]
        for prefix in IGNORED_RESOURCE_PREFIXES:
            if resource_type == prefix or resource_type.startswith(prefix):
                return f"recurso OLM/catalogo ({resource_type})"

    if "replicasets" in parts:
        return "ReplicaSet histórico (não é fonte canônica de workload)"

    if path.suffix.lower() not in COUNTED_EXTENSIONS:
        return f"extensão não suportada ({path.suffix})"

    if not _is_processable_file(path, namespace_root):
        return "categoria não processada nesta camada de ingestão"

    return None


def _is_processable_file(path: Path, namespace_root: Path) -> bool:
    try:
        rel = path.relative_to(namespace_root)
    except ValueError:
        return False

    parts = rel.parts
    if len(parts) < 3:
        return False

    if parts[0] == "apps":
        if parts[1] in IGNORED_APP_DIRS:
            return False
        processable_app_subdirs = (
            "deployments",
            "statefulsets",
            "daemonsets",
            "deploymentconfigs",
            "jobs",
            "cronjobs",
            "replicationcontrollers",
            "pods",
            "pods.metrics.k8s.io",
            "pod-metrics",
            "persistentvolumeclaims",
            "pvc",
            "secrets",
            "hpa",
            "vpa",
            "pdb",
        )
        if len(parts) >= 4 and parts[2] in processable_app_subdirs and path.suffix.lower() in (
            ".yaml",
            ".yml",
        ):
            return True
        if len(parts) >= 4 and parts[2] in (
            "services",
            "routes",
            "configmaps",
            "pod-logs",
        ):
            if parts[2] == "pod-logs" and path.suffix.lower() == ".log":
                return True
            if path.suffix.lower() in (".yaml", ".yml"):
                return True

    if parts[0] == "resources" and len(parts) >= 3:
        if parts[1] in ("pods", "pods.metrics.k8s.io") and path.suffix.lower() in (
            ".yaml",
            ".yml",
        ):
            return True
        processable_resource_dirs = (
            "services",
            "configmaps",
            "secrets",
            "routes.route.openshift.io",
            "clusterserviceversions.operators.coreos.com",
            "packagemanifests.packages.operators.coreos.com",
            "deployments.apps",
            "statefulsets.apps",
            "daemonsets.apps",
            "deploymentconfigs.apps.openshift.io",
            "jobs.batch",
            "cronjobs.batch",
            "replicationcontrollers",
            "horizontalpodautoscalers.autoscaling",
            "verticalpodautoscalers.autoscaling.k8s.io",
            "poddisruptionbudgets.policy",
            "events",
            "events.events.k8s.io",
        )
        if parts[1] in processable_resource_dirs and path.suffix.lower() in (
            ".yaml",
            ".yml",
        ):
            return True

    return False


def scan_namespace_files(namespace_root: Path) -> NamespaceFileInventory:
    """Varre o namespace e classifica arquivos encontrados, processáveis e ignorados."""
    if not namespace_root.is_dir():
        raise FileNotFoundError(f"Diretório do namespace não encontrado: {namespace_root}")

    namespace = namespace_root.name
    found: list[str] = []
    to_process: list[str] = []
    ignored: list[IgnoredFile] = []

    for path in sorted(namespace_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in COUNTED_EXTENSIONS:
            continue

        found.append(str(path))
        reason = _is_ignored_path(path, namespace_root)
        if reason:
            ignored.append(IgnoredFile(file_path=str(path), reason=reason))
        elif _is_processable_file(path, namespace_root):
            to_process.append(str(path))

    return NamespaceFileInventory(
        namespace=namespace,
        root=str(namespace_root),
        files_found=tuple(found),
        files_to_process=tuple(to_process),
        files_ignored=tuple(ignored),
    )
