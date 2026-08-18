"""Resolução de cadeia de ownership Pod → controller canônico."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReplicaSetInfo:
    name: str
    parent_kind: str | None
    parent_name: str | None
    match_labels: dict[str, str] = field(default_factory=dict)


def infer_deployment_from_replicaset_name(rs_name: str) -> str | None:
    """ReplicaSet: <deployment>-<hash> → nome do Deployment."""
    parts = rs_name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isalnum():
        return parts[0]
    return None


def resolve_workload_from_owner(
    owner_kind: str,
    owner_name: str,
    rs_index: dict[str, ReplicaSetInfo],
) -> tuple[str, str] | None:
    """Resolve (workload_name, workload_kind) a partir de ownerReference."""
    if owner_kind == "ReplicaSet":
        rs_info = rs_index.get(owner_name)
        if rs_info and rs_info.parent_name and rs_info.parent_kind:
            return rs_info.parent_name, rs_info.parent_kind
        inferred = infer_deployment_from_replicaset_name(owner_name)
        if inferred:
            return inferred, "Deployment"
        return owner_name, "ReplicaSet"

    if owner_kind in (
        "Deployment",
        "StatefulSet",
        "DaemonSet",
        "DeploymentConfig",
        "Job",
        "CronJob",
        "ReplicationController",
    ):
        return owner_name, owner_kind

    return None


def workload_name_from_pod(pod_name: str) -> str:
    """Fallback: <workload>-<rs-hash>-<pod-suffix> → workload."""
    parts = pod_name.split("-")
    if len(parts) >= 3:
        return "-".join(parts[:-2])
    return pod_name
