"""Classificação de QoS conforme regras do Kubernetes."""

from __future__ import annotations

from kubeoptix_core_ai.models.workload import ContainerSpec

QOS_GUARANTEED = "Guaranteed"
QOS_BURSTABLE = "Burstable"
QOS_BEST_EFFORT = "BestEffort"


def classify_qos(containers: tuple[ContainerSpec, ...]) -> str:
    """
    Classifica QoS a partir de requests/limits dos containers.

    Regras (Kubernetes):
    - Guaranteed: request == limit para CPU e memória em todos os containers
    - BestEffort: nenhum request/limit em nenhum container
    - Burstable: demais casos
    """
    if not containers:
        return QOS_BEST_EFFORT

    has_any_resources = False
    all_guaranteed = True

    for container in containers:
        cpu_req = container.cpu_request
        cpu_lim = container.cpu_limit
        mem_req = container.memory_request
        mem_lim = container.memory_limit

        if any([cpu_req, cpu_lim, mem_req, mem_lim]):
            has_any_resources = True

        if not (cpu_req and cpu_lim and mem_req and mem_lim):
            all_guaranteed = False
            continue

        cpu_match = cpu_req.raw == cpu_lim.raw
        mem_match = mem_req.raw == mem_lim.raw
        if not (cpu_match and mem_match):
            all_guaranteed = False

    if not has_any_resources:
        return QOS_BEST_EFFORT
    if all_guaranteed:
        return QOS_GUARANTEED
    return QOS_BURSTABLE
