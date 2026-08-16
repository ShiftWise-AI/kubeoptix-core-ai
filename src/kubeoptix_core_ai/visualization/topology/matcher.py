"""Matching conservador entre Services e Workloads."""

from __future__ import annotations

from kubeoptix_core_ai.models.inventory import ServiceSpec
from kubeoptix_core_ai.models.workload import Workload


def selector_matches_labels(selector: dict[str, str], labels: dict[str, str]) -> bool:
    """
    Verifica se todos os pares do seletor do Service estão presentes nos labels.

    Match exato — sem inferência por nome ou namespace.
    """
    if not selector:
        return False
    if not labels:
        return False
    return all(labels.get(key) == value for key, value in selector.items())


def workload_pod_labels(workload: Workload) -> dict[str, str]:
    """Labels usados para matching Service→Pod (template do Deployment)."""
    if workload.pod_template_labels:
        return dict(workload.pod_template_labels)
    return dict(workload.match_labels)


def services_for_workload(
    workload: Workload,
    services: tuple[ServiceSpec, ...],
) -> tuple[ServiceSpec, ...]:
    labels = workload_pod_labels(workload)
    if not labels:
        return ()
    return tuple(
        svc for svc in services if selector_matches_labels(svc.selector, labels)
    )


def workloads_for_service(
    service: ServiceSpec,
    workloads: tuple[Workload, ...],
) -> tuple[Workload, ...]:
    if not service.selector:
        return ()
    return tuple(
        wl
        for wl in workloads
        if selector_matches_labels(service.selector, workload_pod_labels(wl))
    )
