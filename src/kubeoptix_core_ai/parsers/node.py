"""Parser de Nodes (v1)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.node import NodeCondition, WorkNode
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.normalize.quantities import parse_cpu_quantity, parse_memory_quantity
from kubeoptix_core_ai.parsers.base import load_yaml_file


_ROLE_LABELS: tuple[tuple[str, str], ...] = (
    ("node-role.kubernetes.io/router", "router"),
    ("node-role.kubernetes.io/3scale", "3scale"),
    ("node-role.kubernetes.io/app", "app"),
    ("node-role.kubernetes.io/storage", "storage"),
    ("node-role.kubernetes.io/infra", "infra"),
)


def _infer_role(labels: dict[str, str]) -> str | None:
    if labels.get("type"):
        return labels["type"]
    for label, role in _ROLE_LABELS:
        if label in labels:
            return role
    return None


def parse_node(file_path: Path) -> WorkNode:
    """Interpreta um arquivo YAML de Node."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "Node":
        raise ParseError(f"kind esperado 'Node', encontrado {kind!r}", file_path=file_path)

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    status = document.get("status") or {}
    spec = document.get("spec") or {}

    name = str(metadata.get("name", file_path.stem))
    labels_raw = metadata.get("labels") or {}
    labels = {str(k): str(v) for k, v in labels_raw.items()} if isinstance(labels_raw, dict) else {}

    capacity = status.get("capacity") or {}
    allocatable = status.get("allocatable") or {}

    cpu_capacity = None
    cpu_allocatable = None
    memory_capacity = None
    memory_allocatable = None

    if "cpu" in capacity:
        cpu_capacity = parse_cpu_quantity(
            capacity["cpu"],
            source=source,
            field_path="status.capacity.cpu",
        )
    if "cpu" in allocatable:
        cpu_allocatable = parse_cpu_quantity(
            allocatable["cpu"],
            source=source,
            field_path="status.allocatable.cpu",
        )
    if "memory" in capacity:
        memory_capacity = parse_memory_quantity(
            capacity["memory"],
            source=source,
            field_path="status.capacity.memory",
        )
    if "memory" in allocatable:
        memory_allocatable = parse_memory_quantity(
            allocatable["memory"],
            source=source,
            field_path="status.allocatable.memory",
        )

    max_pods = None
    if "pods" in allocatable:
        try:
            max_pods = int(str(allocatable["pods"]))
        except ValueError:
            max_pods = None

    conditions: list[NodeCondition] = []
    ready: bool | None = None
    for cond in status.get("conditions") or []:
        if not isinstance(cond, dict):
            continue
        condition = NodeCondition(
            type=str(cond.get("type", "")),
            status=str(cond.get("status", "")),
            reason=cond.get("reason"),
            message=cond.get("message"),
        )
        conditions.append(condition)
        if condition.type == "Ready":
            ready = condition.status == "True"

    taints_raw = spec.get("taints") or []
    taints = tuple(t for t in taints_raw if isinstance(t, dict))

    node_info = status.get("nodeInfo") or {}
    annotations_raw = metadata.get("annotations") or {}
    annotations = (
        {str(k): str(v) for k, v in annotations_raw.items()}
        if isinstance(annotations_raw, dict)
        else {}
    )

    return WorkNode(
        name=name,
        labels=labels,
        datacenter=labels.get("datacenter"),
        role=_infer_role(labels),
        env=labels.get("env"),
        architecture=labels.get("kubernetes.io/arch"),
        cpu_capacity=cpu_capacity,
        cpu_allocatable=cpu_allocatable,
        memory_capacity=memory_capacity,
        memory_allocatable=memory_allocatable,
        max_pods=max_pods,
        conditions=tuple(conditions),
        taints=taints,
        ready=ready,
        kubelet_version=(
            str(node_info["kubeletVersion"])
            if node_info.get("kubeletVersion") is not None
            else None
        ),
        os_image=(
            str(node_info["osImage"]) if node_info.get("osImage") is not None else None
        ),
        container_runtime=(
            str(node_info["containerRuntimeVersion"])
            if node_info.get("containerRuntimeVersion") is not None
            else None
        ),
        mco_state=annotations.get("machineconfiguration.openshift.io/state"),
        mco_current_config=annotations.get(
            "machineconfiguration.openshift.io/currentConfig"
        ),
        mco_desired_config=annotations.get(
            "machineconfiguration.openshift.io/desiredConfig"
        ),
        source=source,
    )
