"""Seleção de manifests YAML para diagramas KubeDiagrams."""

from __future__ import annotations

import os
import re
from pathlib import Path

from kubeoptix_core_ai.discovery.apps import merge_file_lists
from kubeoptix_core_ai.discovery.scanner import discover_namespace
from kubeoptix_core_ai.normalize.ownership import infer_deployment_from_replicaset_name
from kubeoptix_core_ai.visualization.kubediagrams.yamlutil import load_diagram_documents

# Controllers de workload canônicos e correlatos presentes no inventário.
_ARCHITECTURE_WORKLOAD_SUBDIRS = frozenset(
    {
        "deployments",
        "statefulsets",
        "daemonsets",
        "deploymentconfigs",
        "jobs",
        "cronjobs",
        "replicationcontrollers",
        "replicasets",
    }
)

_ARCHITECTURE_RESOURCE_DIRS = frozenset(
    {
        "deployments.apps",
        "statefulsets.apps",
        "daemonsets.apps",
        "deploymentconfigs.apps.openshift.io",
        "jobs.batch",
        "cronjobs.batch",
        "replicationcontrollers",
        "replicasets.apps",
    }
)

_ARCHITECTURE_SUPPORTING_RESOURCES = (
    "service_files",
    "route_files",
    "pod_files",
    "configmap_files",
    "secret_files",
    "pvc_files",
    "hpa_files",
    "vpa_files",
    "pdb_files",
)

_EXTRA_RESOURCE_DIRS = (
    "ingresses.networking.k8s.io",
    "networkpolicies.networking.k8s.io",
    "persistentvolumes",
    "storageclasses.storage.k8s.io",
    "serviceaccounts",
)

_EXTRA_APP_SUBDIRS = (
    "ingresses",
    "networkpolicies",
    "serviceaccounts",
    "persistentvolumeclaims",
    "pvc",
)

_NOISY_DERIVED_DIR_MARKERS = (
    "/endpointslices.discovery.k8s.io/",
    "/endpoints/",
    "/leases.coordination.k8s.io/",
    "/controllerrevisions.apps/",
    "/events.events.k8s.io/",
    "/pods.metrics.k8s.io/",
)

_PLATFORM_NOISE_SUBDIRS = (
    "/configmaps/",
    "/secrets/",
    "/serviceaccounts/",
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
_COMMON_OCP_SERVICE_ACCOUNTS = frozenset(
    {
        "default",
        "builder",
        "deployer",
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

# Camadas do inventário (o layout visual é ajustado no renderer).
_LAYER_ORDER = {
    "configmap": 0,
    "secret": 0,
    "sa": 0,
    "workload": 1,
    "hpa": 2,
    "vpa": 2,
    "pdb": 2,
    "job": 2,
    "cronjob": 2,
    "pod": 3,
    "route": 4,
    "lb": 4,
    "ingress": 4,
    "service": 4,
    "network_policy": 4,
    "pvc": 5,
    "pv": 5,
    "storage_class": 5,
    "rbac": 7,
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

    A ordem agrupa o inventário por camada (config, workload, pod, rede, storage);
    o posicionamento visual (esquerda/direita) é aplicado no renderer.
    """
    return tuple(
        sorted(
            paths,
            key=lambda path: (_manifest_layer(path), str(path).lower()),
        )
    )


def _is_build_artifact(path: Path) -> bool:
    """BuildConfigs, Builds, ImageStreams e pods de build OpenShift."""
    raw = str(path).lower()
    if any(
        marker in raw
        for marker in (
            "/buildconfigs",
            "/builds.build.openshift.io/",
            "/imagestreams.image.openshift.io/",
            "/imagestreams/",
        )
    ):
        return True
    if "/pods/" in raw and path.stem.lower().endswith("-build"):
        return True
    return False


def _is_noisy_derived_path(path: Path) -> bool:
    raw = str(path).lower()
    return any(marker in raw for marker in _NOISY_DERIVED_DIR_MARKERS)


def _is_common_ocp_artifact(path: Path) -> bool:
    """Filtra artefatos padrão de plataforma que poluem a arquitetura."""
    raw = str(path).lower()
    stem = path.stem.lower()
    if any(segment in raw for segment in _GLOBAL_NO_APP_SEGMENTS):
        if "/resources/namespaces/" in raw:
            return True
        if any(subdir in raw for subdir in _PLATFORM_NOISE_SUBDIRS):
            return True

    if "/configmaps/" in raw and (
        stem in _COMMON_OCP_CONFIGMAPS
        or stem.endswith("-ca")
        or stem.endswith("-global-ca")
        or stem.endswith("-sys-config")
    ):
        return True
    if "/secrets/" in raw:
        if stem in _COMMON_OCP_SECRETS:
            return True
        if _SERVICE_ACCOUNT_TOKEN_PATTERN.match(stem):
            return True
    if "/serviceaccounts/" in raw and stem in _COMMON_OCP_SERVICE_ACCOUNTS:
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


def _is_controller_path(path: Path) -> bool:
    raw = str(path).lower()
    markers = (
        "/deployments/",
        "/deployments.apps/",
        "/statefulsets/",
        "/statefulsets.apps/",
        "/daemonsets/",
        "/daemonsets.apps/",
        "/deploymentconfigs/",
        "/deploymentconfigs.apps.openshift.io/",
        "/replicationcontrollers/",
        "/cronjobs/",
        "/cronjobs.batch/",
    )
    return any(marker in raw for marker in markers)


def _is_replicaset_path(path: Path) -> bool:
    raw = str(path).lower()
    return "/replicasets/" in raw or "/replicasets.apps/" in raw


def _peek_kind_and_owners(path: Path) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    documents = load_diagram_documents(path)
    document = next((item for item in documents if item.get("kind")), None)
    if not isinstance(document, dict):
        return None, ()
    kind = str(document.get("kind") or "") or None
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        return kind, ()
    owners_raw = metadata.get("ownerReferences")
    owners: list[tuple[str, str]] = []
    if isinstance(owners_raw, list):
        for owner in owners_raw:
            if not isinstance(owner, dict):
                continue
            owner_kind = str(owner.get("kind") or "")
            owner_name = str(owner.get("name") or "")
            if owner_kind and owner_name:
                owners.append((owner_kind, owner_name))
    return kind, tuple(owners)


def _prefer_resources_path(existing: Path, candidate: Path) -> Path:
    if "/resources/" in str(candidate) and "/resources/" not in str(existing):
        return candidate
    return existing


def _dedupe_by_kind_and_name(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    """Um objeto (kind + nome) entra uma vez; `resources/` tem precedência."""
    seen: dict[str, Path] = {}
    order: list[str] = []
    for path in paths:
        kind, _ = _peek_kind_and_owners(path)
        key = f"{kind or 'unknown'}:{path.stem.lower()}"
        if key not in seen:
            order.append(key)
            seen[key] = path
            continue
        seen[key] = _prefer_resources_path(seen[key], path)
    return tuple(seen[key] for key in order)


def _filter_derived_replicasets(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    """Remove ReplicaSets intermediários quando o controller dono já está no diagrama."""
    controller_names = {path.stem for path in paths if _is_controller_path(path)}
    kept: list[Path] = []
    for path in paths:
        if not _is_replicaset_path(path):
            kept.append(path)
            continue
        kind, owners = _peek_kind_and_owners(path)
        if kind != "ReplicaSet":
            kept.append(path)
            continue
        owned_by_selected = any(
            owner_kind in {"Deployment", "DeploymentConfig"} and owner_name in controller_names
            for owner_kind, owner_name in owners
        )
        inferred = infer_deployment_from_replicaset_name(path.stem)
        if owned_by_selected or (inferred is not None and inferred in controller_names):
            continue
        kept.append(path)
    return tuple(kept)


def _platform_route_files(namespace_root: Path) -> tuple[Path, ...]:
    """Routes em ``apps/__sem_app__/routes`` (plataforma OpenShift)."""
    routes_dir = namespace_root / "apps" / "__sem_app__" / "routes"
    if not routes_dir.is_dir():
        return ()
    return tuple(sorted(routes_dir.glob("*.yaml")))


def _collect_named_dirs(
    namespace_root: Path,
    resource_dirs: tuple[str, ...],
    app_subdirs: tuple[str, ...],
) -> tuple[Path, ...]:
    selected: list[Path] = []
    for resource_dir in resource_dirs:
        res_dir = namespace_root / "resources" / resource_dir
        if res_dir.is_dir():
            selected.extend(sorted(res_dir.glob("*.yaml")))
    apps_dir = namespace_root / "apps"
    if apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            if not app_dir.is_dir():
                continue
            for subdir in app_subdirs:
                target = app_dir / subdir
                if target.is_dir():
                    selected.extend(sorted(target.glob("*.yaml")))
    return tuple(selected)


def select_architecture_manifests(namespace_root: Path) -> tuple[Path, ...]:
    """
    Seleciona YAMLs do inventário para o diagrama de arquitetura do namespace.

    Inclui workloads, pods (depois agrupados), networking, storage e
    configuração presentes nos arquivos. Não inventa objetos. Exclui artefatos
    de plataforma, recursos de Build e recursos derivados ruidosos
    (Endpoints, Leases, ReplicaSets intermediários).
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
        _collect_named_dirs(namespace_root, _EXTRA_RESOURCE_DIRS, _EXTRA_APP_SUBDIRS),
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
            if _is_build_artifact(path):
                continue
            if _is_noisy_derived_path(path):
                continue
            if not include_common and _is_common_ocp_artifact(path):
                continue
        filtered.append(path)
    return _sort_for_architecture(
        _filter_derived_replicasets(_dedupe_by_kind_and_name(tuple(filtered)))
    )
