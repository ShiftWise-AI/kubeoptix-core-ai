"""Testes de matching Service→Workload."""

from __future__ import annotations

from kubeoptix_analyzer.models.inventory import ServicePortSpec, ServiceSpec
from kubeoptix_analyzer.models.source import DataSourceRef
from kubeoptix_analyzer.models.workload import Workload
from kubeoptix_analyzer.visualization.topology.matcher import (
    selector_matches_labels,
    services_for_workload,
    workloads_for_service,
)


def _source(name: str = "test") -> DataSourceRef:
    return DataSourceRef(
        file_path=f"/tmp/{name}.yaml",
        resource_kind="Service",
        resource_name=name,
    )


def _workload(name: str, labels: dict[str, str]) -> Workload:
    return Workload(
        namespace="ns",
        name=name,
        app_group=name,
        kind="Deployment",
        pod_template_labels=labels,
        source=_source(name),
    )


def _service(name: str, selector: dict[str, str]) -> ServiceSpec:
    return ServiceSpec(
        name=name,
        namespace="ns",
        selector=selector,
        ports=(ServicePortSpec(port=8080),),
        source=_source(name),
    )


def test_selector_matches_exact() -> None:
    assert selector_matches_labels({"app": "foo"}, {"app": "foo", "version": "1"})
    assert not selector_matches_labels({"app": "foo"}, {"app": "bar"})
    assert not selector_matches_labels({"app": "foo"}, {})
    assert not selector_matches_labels({}, {"app": "foo"})


def test_services_for_workload_no_inference_by_name() -> None:
    wl = _workload("backend", {"app": "backend"})
    svc_match = _service("backend", {"app": "backend"})
    svc_miss = _service("backend", {"app": "other"})
    matched = services_for_workload(wl, (svc_match, svc_miss))
    assert len(matched) == 1
    assert matched[0].name == "backend"


def test_workloads_for_service_requires_labels() -> None:
    wl = _workload("api", {"app": "api"})
    wl_no_labels = _workload("orphan", {})
    svc = _service("api-svc", {"app": "api"})
    matched = workloads_for_service(svc, (wl, wl_no_labels))
    assert len(matched) == 1
    assert matched[0].name == "api"
