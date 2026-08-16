"""Testes de classificação QoS."""

from __future__ import annotations

from kubeoptix_core_ai.models.quantities import ResourceQuantity
from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef
from kubeoptix_core_ai.models.workload import ContainerSpec
from kubeoptix_core_ai.normalize.qos import (
    QOS_BEST_EFFORT,
    QOS_BURSTABLE,
    QOS_GUARANTEED,
    classify_qos,
)

FIELD = FieldRef(file_path="/tmp/t.yaml", field_path="spec.cpu", raw_value="100m")
CONTAINER_SOURCE = DataSourceRef(
    file_path="/tmp/t.yaml",
    resource_kind="Deployment",
    resource_name="test",
    namespace="test-ns",
)


def _cpu(raw: str) -> ResourceQuantity:
    return ResourceQuantity(
        raw=raw,
        resource_kind="cpu",
        normalized_value=100.0,
        display_unit="m",
        source=FIELD,
    )


def _mem(raw: str) -> ResourceQuantity:
    return ResourceQuantity(
        raw=raw,
        resource_kind="memory",
        normalized_value=1024.0,
        display_unit="Mi",
        source=FIELD,
    )


def test_qos_guaranteed() -> None:
    container = ContainerSpec(
        name="c",
        cpu_request=_cpu("100m"),
        cpu_limit=_cpu("100m"),
        memory_request=_mem("128Mi"),
        memory_limit=_mem("128Mi"),
        source=CONTAINER_SOURCE,
    )
    assert classify_qos((container,)) == QOS_GUARANTEED


def test_qos_burstable() -> None:
    container = ContainerSpec(
        name="c",
        cpu_request=_cpu("100m"),
        cpu_limit=_cpu("200m"),
        memory_request=_mem("128Mi"),
        memory_limit=_mem("256Mi"),
        source=CONTAINER_SOURCE,
    )
    assert classify_qos((container,)) == QOS_BURSTABLE


def test_qos_best_effort() -> None:
    container = ContainerSpec(name="c", source=CONTAINER_SOURCE)
    assert classify_qos((container,)) == QOS_BEST_EFFORT
