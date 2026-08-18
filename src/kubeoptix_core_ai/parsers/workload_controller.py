"""Parser genérico de controllers de workload com pod template."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.models.workload import Workload
from kubeoptix_core_ai.parsers.base import load_yaml_file
from kubeoptix_core_ai.parsers.workload_common import (
    extract_resource_refs,
    parse_container,
    parse_volume_mounts,
    parse_volumes,
)

# Kinds que representam workloads canônicos (não intermediários).
CANONICAL_WORKLOAD_KINDS = frozenset({
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "DeploymentConfig",
    "Job",
    "CronJob",
    "ReplicationController",
})

# ReplicaSet é recurso intermediário — usado apenas para correlação.
INTERMEDIATE_WORKLOAD_KINDS = frozenset({"ReplicaSet"})

SUPPORTED_WORKLOAD_KINDS = CANONICAL_WORKLOAD_KINDS | INTERMEDIATE_WORKLOAD_KINDS


def _template_paths(kind: str) -> tuple[str, str]:
    """Retorna (spec_path_prefix, template_base) para extrair pod template."""
    if kind == "CronJob":
        return "spec.jobTemplate.spec", "spec.jobTemplate.spec.template.spec"
    if kind == "Job":
        return "spec", "spec.template.spec"
    return "spec", "spec.template.spec"


def _replica_status_fields(kind: str, spec: dict, status: dict) -> tuple[int | None, int | None, int | None]:
    """Extrai réplicas desejadas, prontas e disponíveis conforme o tipo."""
    desired: int | None = None
    ready: int | None = None
    available: int | None = None

    if kind in ("Deployment", "StatefulSet", "ReplicationController", "DeploymentConfig"):
        raw = spec.get("replicas")
        if raw is not None:
            desired = int(raw)
        raw_ready = status.get("readyReplicas")
        if raw_ready is not None:
            ready = int(raw_ready)
        raw_avail = status.get("availableReplicas")
        if raw_avail is not None:
            available = int(raw_avail)
    elif kind == "DaemonSet":
        raw = status.get("desiredNumberScheduled")
        if raw is not None:
            desired = int(raw)
        raw_ready = status.get("numberReady")
        if raw_ready is not None:
            ready = int(raw_ready)
        raw_avail = status.get("numberAvailable")
        if raw_avail is not None:
            available = int(raw_avail)
    elif kind == "Job":
        completions = spec.get("completions")
        if completions is not None:
            desired = int(completions)
        elif spec.get("parallelism") is not None:
            desired = int(spec["parallelism"])
        succeeded = status.get("succeeded")
        if succeeded is not None:
            ready = int(succeeded)
    elif kind == "CronJob":
        # CronJob não tem réplicas — schedule é o campo relevante
        pass
    elif kind == "ReplicaSet":
        raw = spec.get("replicas")
        if raw is not None:
            desired = int(raw)
        raw_ready = status.get("readyReplicas")
        if raw_ready is not None:
            ready = int(raw_ready)
        raw_avail = status.get("availableReplicas")
        if raw_avail is not None:
            available = int(raw_avail)

    return desired, ready, available


def _update_strategy(kind: str, spec: dict) -> str | None:
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "DeploymentConfig"):
        strategy = spec.get("strategy") or spec.get("updateStrategy")
        if isinstance(strategy, dict):
            stype = strategy.get("type")
            return str(stype) if stype is not None else None
    return None


def _match_labels(kind: str, spec: dict) -> dict[str, str]:
    if kind == "CronJob":
        selector = (spec.get("jobTemplate") or {}).get("spec", {}).get("selector", {})
    elif kind == "Job":
        selector = spec.get("selector") or {}
    else:
        selector = spec.get("selector") or {}

    if isinstance(selector, dict) and "matchLabels" in selector:
        match_labels_raw = selector.get("matchLabels") or {}
    elif isinstance(selector, dict):
        match_labels_raw = selector
    else:
        match_labels_raw = {}

    if not isinstance(match_labels_raw, dict):
        match_labels_raw = {}
    return {str(k): str(v) for k, v in match_labels_raw.items()}


def _pod_template_metadata(kind: str, spec: dict) -> dict[str, str]:
    if kind == "CronJob":
        template_metadata = (
            (spec.get("jobTemplate") or {}).get("spec", {}).get("template", {}).get("metadata") or {}
        )
    elif kind == "Job":
        template_metadata = (spec.get("template") or {}).get("metadata") or {}
    else:
        template_metadata = (spec.get("template") or {}).get("metadata") or {}

    pod_labels_raw = template_metadata.get("labels") or {}
    if not isinstance(pod_labels_raw, dict):
        pod_labels_raw = {}
    return {str(k): str(v) for k, v in pod_labels_raw.items()}


def _template_spec(kind: str, spec: dict) -> dict:
    if kind == "CronJob":
        return (
            (spec.get("jobTemplate") or {})
            .get("spec", {})
            .get("template", {})
            .get("spec", {})
            or {}
        )
    if kind == "Job":
        return (spec.get("template") or {}).get("spec") or {}
    return (spec.get("template") or {}).get("spec") or {}


def parse_workload_controller(
    file_path: Path,
    *,
    app_group: str | None = None,
    expected_kind: str | None = None,
) -> Workload:
    """Interpreta um controller de workload (Deployment, StatefulSet, Job, etc.)."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind not in SUPPORTED_WORKLOAD_KINDS:
        raise ParseError(
            f"kind de workload não suportado: {kind!r}",
            file_path=file_path,
        )
    if expected_kind is not None and kind != expected_kind:
        raise ParseError(
            f"kind esperado {expected_kind!r}, encontrado {kind!r}",
            file_path=file_path,
        )

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    status = document.get("status") or {}

    namespace = str(metadata.get("namespace", ""))
    name = str(metadata.get("name", file_path.stem))
    group = app_group or name

    _, template_base = _template_paths(kind)
    template_spec = _template_spec(kind, spec)
    containers_data = template_spec.get("containers") or []
    if not isinstance(containers_data, list):
        raise ParseError(
            f"{template_base}.containers deve ser uma lista",
            file_path=file_path,
        )

    containers = tuple(
        parse_container(container, idx, source, base_prefix=template_base)
        for idx, container in enumerate(containers_data)
        if isinstance(container, dict)
    )

    node_selector = template_spec.get("nodeSelector") or {}
    if not isinstance(node_selector, dict):
        node_selector = {}
    node_selector_normalized = {str(k): str(v) for k, v in node_selector.items()}

    match_labels = _match_labels(kind, spec)
    pod_template_labels = _pod_template_metadata(kind, spec)

    affinity = template_spec.get("affinity")
    tolerations = template_spec.get("tolerations")
    topology = template_spec.get("topologySpreadConstraints")

    replicas_desired, replicas_ready, replicas_available = _replica_status_fields(
        kind, spec, status
    )

    volumes = parse_volumes(template_spec, source, template_base)
    volume_mounts = parse_volume_mounts(containers_data, source, template_base)
    referenced_configmaps, referenced_secrets, image_pull_secrets = extract_resource_refs(
        template_spec, containers_data
    )

    schedule = None
    if kind == "CronJob":
        raw_schedule = spec.get("schedule")
        if raw_schedule is not None:
            schedule = str(raw_schedule)

    parent_cronjob = None
    if kind == "Job":
        for owner in metadata.get("ownerReferences") or []:
            if isinstance(owner, dict) and owner.get("kind") == "CronJob":
                parent_cronjob = str(owner.get("name", ""))
                break

    return Workload(
        namespace=namespace,
        name=name,
        app_group=group,
        kind=str(kind),
        replicas_desired=replicas_desired,
        replicas_ready=replicas_ready,
        replicas_available=replicas_available,
        containers=containers,
        node_selector=node_selector_normalized,
        pod_template_labels=pod_template_labels,
        match_labels=match_labels,
        affinity=affinity if isinstance(affinity, dict) else None,
        tolerations=tolerations if isinstance(tolerations, list) else None,
        topology_spread_constraints=topology if isinstance(topology, list) else None,
        volumes=volumes,
        volume_mounts=volume_mounts,
        referenced_configmaps=referenced_configmaps,
        referenced_secrets=referenced_secrets,
        image_pull_secrets=image_pull_secrets,
        update_strategy=_update_strategy(kind, spec),
        schedule=schedule,
        parent_cronjob=parent_cronjob,
        source=source,
    )
