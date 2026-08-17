"""Correlação centralizada entre pods, controllers e recursos operacionais."""

from __future__ import annotations

from kubeoptix_core_ai.models.workload import (
    HPASpec,
    PDBSpec,
    PodPlacement,
    VPASpec,
    Workload,
)
from kubeoptix_core_ai.normalize.ownership import (
    ReplicaSetInfo,
    infer_deployment_from_replicaset_name,
    workload_name_from_pod,
)


def build_replicaset_index(workloads: list[Workload]) -> dict[str, ReplicaSetInfo]:
    index: dict[str, ReplicaSetInfo] = {}
    for wl in workloads:
        if wl.kind != "ReplicaSet":
            continue
        parent_kind = None
        parent_name = None
        inferred = infer_deployment_from_replicaset_name(wl.name)
        if inferred:
            parent_kind = "Deployment"
            parent_name = inferred
        index[wl.name] = ReplicaSetInfo(
            name=wl.name,
            parent_kind=parent_kind,
            parent_name=parent_name,
            match_labels=dict(wl.match_labels),
        )
    return index


def correlate_pod_placements(
    placements: list[PodPlacement],
) -> dict[str, list[PodPlacement]]:
    """Agrupa placements por nome do workload canônico."""
    by_workload: dict[str, list[PodPlacement]] = {}
    for placement in placements:
        workload_name = placement.workload_name
        if workload_name:
            by_workload.setdefault(workload_name, []).append(placement)
    return by_workload


def correlate_metrics_by_workload(
    metrics_by_pod: dict[str, list],
    placements: list[PodPlacement],
) -> dict[str, list]:
    """Mapeia métricas de pod para workload canônico."""
    pod_to_workload: dict[str, str] = {}
    for placement in placements:
        if placement.workload_name:
            pod_to_workload[placement.pod_name] = placement.workload_name

    by_workload: dict[str, list] = {}
    for pod_name, snapshots in metrics_by_pod.items():
        workload_name = pod_to_workload.get(pod_name)
        if workload_name is None:
            workload_name = workload_name_from_pod(pod_name)
        by_workload.setdefault(workload_name, []).extend(snapshots)
    return by_workload


def correlate_autoscalers(
    hpas: list[HPASpec],
    vpas: list[VPASpec],
) -> tuple[dict[str, HPASpec], dict[str, VPASpec]]:
    hpa_by_target: dict[str, HPASpec] = {}
    for hpa in hpas:
        if hpa.target_workload_name:
            hpa_by_target[hpa.target_workload_name] = hpa

    vpa_by_target: dict[str, VPASpec] = {}
    for vpa in vpas:
        if vpa.target_workload_name:
            vpa_by_target[vpa.target_workload_name] = vpa

    return hpa_by_target, vpa_by_target


def correlate_pdbs(
    pdbs: list[PDBSpec],
    workloads: list[Workload],
) -> dict[str, PDBSpec]:
    """Associa PDB ao workload cujos labels são cobertos pelo seletor do PDB."""
    result: dict[str, PDBSpec] = {}
    for pdb in pdbs:
        if not pdb.selector:
            continue
        for wl in workloads:
            if _selector_matches(pdb.selector, wl.match_labels) or _selector_matches(
                pdb.selector, wl.pod_template_labels
            ):
                result[wl.name] = pdb
    return result


def _selector_matches(selector: dict[str, str], labels: dict[str, str]) -> bool:
    if not selector or not labels:
        return False
    return all(labels.get(k) == v for k, v in selector.items())


def filter_canonical_workloads(workloads: list[Workload]) -> list[Workload]:
    """
    Remove recursos intermediários e Jobs filhos de CronJob.

    ReplicaSet nunca é workload canônico.
    Job com parent_cronjob é representado pelo CronJob pai.
    """
    canonical_kinds = {
        "Deployment",
        "StatefulSet",
        "DaemonSet",
        "DeploymentConfig",
        "CronJob",
        "ReplicationController",
        "Job",
    }
    filtered: list[Workload] = []
    for wl in workloads:
        if wl.kind == "ReplicaSet":
            continue
        if wl.kind not in canonical_kinds:
            continue
        if wl.kind == "Job" and wl.parent_cronjob:
            continue
        filtered.append(wl)
    return filtered


def enrich_workloads_with_correlations(
    workloads: list[Workload],
    placements_by_workload: dict[str, list[PodPlacement]],
    metrics_by_workload: dict[str, list],
    qos_by_workload: dict[str, str],
    hpa_by_target: dict[str, HPASpec],
    vpa_by_target: dict[str, VPASpec],
    pdb_by_workload: dict[str, PDBSpec],
) -> list[Workload]:
    enriched: list[Workload] = []
    for wl in workloads:
        enriched.append(
            wl.model_copy(
                update={
                    "hpa": hpa_by_target.get(wl.name),
                    "vpa": vpa_by_target.get(wl.name),
                    "pdb": pdb_by_workload.get(wl.name),
                    "placements": tuple(placements_by_workload.get(wl.name, ())),
                    "metrics": tuple(metrics_by_workload.get(wl.name, ())),
                    "qos_class": qos_by_workload.get(wl.name),
                }
            )
        )
    return enriched
