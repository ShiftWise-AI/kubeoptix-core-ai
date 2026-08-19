"""Seleção de manifests YAML para diagramas KubeDiagrams."""

from __future__ import annotations

import os
import re
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

# Recursos de comunicação e execução para o diagrama simplificado.
_ARCHITECTURE_SUPPORTING_RESOURCES = (
    "service_files",
    "route_files",
    "pod_files",
)

_COMMUNICATION_RESOURCE_DIRS = (
    "ingresses.networking.k8s.io",
)

_COMMON_OCP_CONFIGMAPS = frozenset(
    {
        "kube-root-ca.crt",
        "openshift-service-ca.crt",
        "trusted-ca-bundle",
        "service-ca",
        "global-ca",
        "sys-config",
    }
)
_COMMON_OCP_SECRETS = frozenset(
    {
        "default-dockercfg",
        "builder-dockercfg",
        "deployer-dockercfg",
        "builder-token",
        "deployer-token",
    }
)
_SERVICE_ACCOUNT_TOKEN_PATTERN = re.compile(r".+-token-[a-z0-9]{4,}$")
_GLOBAL_NO_APP_SEGMENTS = (
    "/apps/__sem_app__/",
    "/apps/_no_app_/",
    "/apps/__no_app__/",
    "/resources/namespaces/",
)
_ENV_INCLUDE_COMMON = "KUBEOPTIX_DIAGRAM_INCLUDE_COMMON_OCP"
_ENV_INCLUDE_PATH_REGEX = "KUBEOPTIX_DIAGRAM_INCLUDE_PATH_REGEX"
_ENV_EXCLUDE_PATH_REGEX = "KUBEOPTIX_DIAGRAM_EXCLUDE_PATH_REGEX"

_LAYER_ORDER = {
    "lb": 0,
    "route": 0,
    "service": 1,
    "ingress": 1,
    "network_policy": 1,
    "workload": 2,
    "rbac": 2,
    "pod": 3,
    "hpa": 4,
    "vpa": 4,
    "pdb": 4,
    "job": 4,
    "cronjob": 4,
    "configmap": 5,
    "secret": 5,
    "pvc": 5,
    "pv": 5,
    "storage_class": 5,
    "sa": 5,
    "other": 9,
}


def _manifest_layer(path: Path) -> int:
    raw = str(path).lower()
    if "/loadbalancers/" in raw:
        return _LAYER_ORDER["lb"]
    if "/routes/" in raw or "/routes.route.openshift.io/" in raw:
        return _LAYER_ORDER["route"]
    if "/services/" in raw:
        return _LAYER_ORDER["service"]
    if "/ingresses.networking.k8s.io/" in raw or "/ingresses/" in raw:
        return _LAYER_ORDER["ingress"]
    if "/networkpolicies.networking.k8s.io/" in raw or "/networkpolicies/" in raw:
        return _LAYER_ORDER["network_policy"]
    if _is_architecture_workload(path):
        return _LAYER_ORDER["workload"]
    if "/roles.rbac.authorization.k8s.io/" in raw or "/rolebindings.rbac.authorization.k8s.io/" in raw:
        return _LAYER_ORDER["rbac"]
    if "/clusterroles.rbac.authorization.k8s.io/" in raw or "/clusterrolebindings.rbac.authorization.k8s.io/" in raw:
        return _LAYER_ORDER["rbac"]
    if "/pods/" in raw:
        return _LAYER_ORDER["pod"]
    if "/horizontalpodautoscalers.autoscaling/" in raw or "/hpa/" in raw:
        return _LAYER_ORDER["hpa"]
    if "/verticalpodautoscalers.autoscaling.k8s.io/" in raw or "/vpa/" in raw:
        return _LAYER_ORDER["vpa"]
    if "/poddisruptionbudgets.policy/" in raw or "/pdb/" in raw:
        return _LAYER_ORDER["pdb"]
    if "/jobs.batch/" in raw or "/jobs/" in raw:
        return _LAYER_ORDER["job"]
    if "/cronjobs.batch/" in raw or "/cronjobs/" in raw:
        return _LAYER_ORDER["cronjob"]
    if "/configmaps/" in raw:
        return _LAYER_ORDER["configmap"]
    if "/secrets/" in raw:
        return _LAYER_ORDER["secret"]
    if "/persistentvolumeclaims/" in raw or "/pvc/" in raw:
        return _LAYER_ORDER["pvc"]
    if "/persistentvolumes/" in raw:
        return _LAYER_ORDER["pv"]
    if "/storageclasses.storage.k8s.io/" in raw or "/storageclasses/" in raw:
        return _LAYER_ORDER["storage_class"]
    if "/serviceaccounts/" in raw:
        return _LAYER_ORDER["sa"]
    return _LAYER_ORDER["other"]


def _sort_for_architecture(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    """
    Ordena manifests por camada arquitetural para facilitar leitura do diagrama.

    A ordem busca favorecer visualmente os fluxos:
    entrada (Route) → exposição (Service) → execução (Workload/Pod) → suporte.
    """
    return tuple(
        sorted(
            paths,
            key=lambda path: (_manifest_layer(path), str(path).lower()),
        )
    )


def _is_common_ocp_artifact(path: Path) -> bool:
    """Filtra artefatos padrão de plataforma que poluem a arquitetura."""
    raw = str(path).lower()
    stem = path.stem.lower()
    if any(segment in raw for segment in _GLOBAL_NO_APP_SEGMENTS):
        return True

    if "/configmaps/" in raw and (
        stem in _COMMON_OCP_CONFIGMAPS
        or stem.endswith("-global-ca")
        or stem.endswith("-sys-config")
    ):
        return True
    if "/secrets/" in raw:
        if stem in _COMMON_OCP_SECRETS:
            return True
        if _SERVICE_ACCOUNT_TOKEN_PATTERN.match(stem):
            return True
    return False


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_regexes(name: str) -> tuple[re.Pattern[str], ...]:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return ()
    patterns: list[re.Pattern[str]] = []
    for item in raw.split(","):
        expr = item.strip()
        if not expr:
            continue
        try:
            patterns.append(re.compile(expr))
        except re.error:
            # Regex inválida não deve quebrar geração de relatório.
            continue
    return tuple(patterns)


def _matches_any(path: Path, patterns: tuple[re.Pattern[str], ...]) -> bool:
    if not patterns:
        return False
    raw = str(path)
    return any(pattern.search(raw) for pattern in patterns)


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


def _communication_ingress_files(namespace_root: Path) -> tuple[Path, ...]:
    """Ingresses usados na camada de entrada HTTP(S)."""
    selected: list[Path] = []
    for resource_dir in _COMMUNICATION_RESOURCE_DIRS:
        res_dir = namespace_root / "resources" / resource_dir
        if res_dir.is_dir():
            selected.extend(sorted(res_dir.glob("*.yaml")))
    apps_dir = namespace_root / "apps"
    if apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            if not app_dir.is_dir():
                continue
            ingress_dir = app_dir / "ingresses"
            if ingress_dir.is_dir():
                selected.extend(sorted(ingress_dir.glob("*.yaml")))
    return tuple(selected)


def select_architecture_manifests(namespace_root: Path) -> tuple[Path, ...]:
    """
    Seleciona YAMLs para o diagrama simplificado de comunicação do namespace.

    Inclui apenas recursos que representam fluxo de comunicação:
    Routes, Ingresses, Services, controllers de workload e Pods (agrupados).
    Exclui ConfigMaps, Secrets, RBAC, storage, autoscalers e artefatos de plataforma.
    """
    if not namespace_root.is_dir():
        return ()

    paths = discover_namespace(namespace_root)
    workload_files = tuple(path for path in paths.workload_files if _is_architecture_workload(path))

    supporting_groups = tuple(
        getattr(paths, attr_name, ())
        for attr_name in _ARCHITECTURE_SUPPORTING_RESOURCES
    )
    merged = merge_file_lists(
        workload_files,
        *supporting_groups,
        _platform_route_files(namespace_root),
        _communication_ingress_files(namespace_root),
    )
    include_common = _env_flag(_ENV_INCLUDE_COMMON, default=False)
    include_patterns = _env_regexes(_ENV_INCLUDE_PATH_REGEX)
    exclude_patterns = _env_regexes(_ENV_EXCLUDE_PATH_REGEX)

    filtered: list[Path] = []
    for path in merged:
        force_include = _matches_any(path, include_patterns)
        if not force_include:
            if _matches_any(path, exclude_patterns):
                continue
            if not include_common and _is_common_ocp_artifact(path):
                continue
        filtered.append(path)
    return _sort_for_architecture(tuple(filtered))
