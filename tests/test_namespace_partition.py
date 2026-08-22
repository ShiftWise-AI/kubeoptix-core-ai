"""Testes da proposta de quebra de namespaces por comunicação."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.analysis.namespace_partition import (
    MIN_WORKLOADS_FOR_SPLIT,
    propose_namespace_partition,
)
from kubeoptix_core_ai.analysis.workload_refs import extract_service_calls
from kubeoptix_core_ai.models.inventory import RouteSpec, ServicePortSpec, ServiceSpec
from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef
from kubeoptix_core_ai.models.storage import VolumeSpec
from kubeoptix_core_ai.models.workload import Workload


def _source(name: str, kind: str = "Deployment") -> DataSourceRef:
    return DataSourceRef(
        file_path=f"/tmp/{name}.yaml",
        resource_kind=kind,
        resource_name=name,
        namespace="big-ns",
    )


def _workload(
    name: str,
    *,
    app_group: str,
    kind: str = "Deployment",
    labels: dict[str, str] | None = None,
    secrets: tuple[str, ...] = (),
    configmaps: tuple[str, ...] = (),
    claim_name: str | None = None,
    file_path: str | None = None,
) -> Workload:
    source = _source(name, kind)
    if file_path is not None:
        source = source.model_copy(update={"file_path": file_path})
    volumes = ()
    if claim_name:
        volumes = (
            VolumeSpec(
                name="data",
                volume_type="persistentVolumeClaim",
                claim_name=claim_name,
                source=FieldRef(file_path=source.file_path, field_path="spec.template.spec.volumes"),
            ),
        )
    return Workload(
        namespace="big-ns",
        name=name,
        app_group=app_group,
        kind=kind,
        pod_template_labels=labels or {"app": name},
        referenced_secrets=secrets,
        referenced_configmaps=configmaps,
        volumes=volumes,
        source=source,
    )


def _service(name: str, selector: dict[str, str]) -> ServiceSpec:
    return ServiceSpec(
        name=name,
        namespace="big-ns",
        selector=selector,
        ports=(ServicePortSpec(port=8080),),
        source=_source(name, "Service"),
    )


def _route(name: str, target: str) -> RouteSpec:
    return RouteSpec(
        name=name,
        namespace="big-ns",
        host=f"{name}.example.com",
        target_service=target,
        source=_source(name, "Route"),
    )


def test_does_not_suggest_split_below_threshold() -> None:
    workloads = tuple(
        _workload(f"app-{i}", app_group="app") for i in range(MIN_WORKLOADS_FOR_SPLIT - 1)
    )
    partition = propose_namespace_partition("big-ns", workloads)
    assert partition.should_split is False
    assert partition.groups == ()
    assert "redistribuição só é sugerida" in (partition.skip_reason or "")


def test_splits_disconnected_app_groups() -> None:
    workloads = (
        *(_workload(f"web-{i}", app_group="frontend", labels={"app": f"web-{i}"}) for i in range(3)),
        *(_workload(f"job-{i}", app_group="batch", kind="CronJob", labels={"app": f"job-{i}"}) for i in range(3)),
    )
    services = (
        _service("web-0", {"app": "web-0"}),
        _service("web-1", {"app": "web-1"}),
        _service("web-2", {"app": "web-2"}),
    )
    routes = (_route("web-public", "web-0"),)
    partition = propose_namespace_partition("big-ns", workloads, services, routes)
    assert partition.should_split is True
    assert len(partition.groups) == 2
    slugs = {group.slug for group in partition.groups}
    names = {name for group in partition.groups for name in group.workload_names}
    assert names == {wl.name for wl in workloads}
    assert "frontend" in slugs or "web" in slugs
    roles = {group.role for group in partition.groups}
    assert "exposição HTTP" in roles
    assert "processamento em lote" in roles


def test_keeps_workloads_together_when_env_calls_connect_groups(
    tmp_path: Path,
) -> None:
    yaml_path = tmp_path / "web-0.yaml"
    yaml_path.write_text(
        """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-0
spec:
  template:
    spec:
      containers:
      - name: app
        env:
        - name: API_URL
          value: http://api-0:8080
""",
        encoding="utf-8",
    )
    workloads = (
        _workload("web-0", app_group="frontend", labels={"app": "web-0"}, file_path=str(yaml_path)),
        _workload("web-1", app_group="frontend", labels={"app": "web-1"}),
        _workload("web-2", app_group="frontend", labels={"app": "web-2"}),
        _workload("api-0", app_group="backend", labels={"app": "api"}),
        _workload("api-1", app_group="backend", labels={"app": "api"}),
        _workload("api-2", app_group="backend", labels={"app": "api"}),
    )
    services = (
        _service("api-0", {"app": "api"}),
        _service("web-0", {"app": "web-0"}),
        _service("web-1", {"app": "web-1"}),
        _service("web-2", {"app": "web-2"}),
    )
    partition = propose_namespace_partition("big-ns", workloads, services)
    # web-0 chama o Service que seleciona os 3 backends → um componente; o
    # restante do frontend continua agrupável. A sugestão pode existir, mas
    # web-0 não pode ser separado dos backends.
    backend_names = {"api-0", "api-1", "api-2"}
    if partition.should_split:
        web0_group = next(
            group for group in partition.groups if "web-0" in group.workload_names
        )
        assert backend_names <= set(web0_group.workload_names)
    else:
        assert any(edge.kind == "env_call" for edge in partition.edges)


def test_platform_configmap_does_not_merge_groups() -> None:
    workloads = (
        *(_workload(f"web-{i}", app_group="frontend", configmaps=("kube-root-ca.crt",)) for i in range(3)),
        *(_workload(f"job-{i}", app_group="batch", configmaps=("kube-root-ca.crt",)) for i in range(3)),
    )
    partition = propose_namespace_partition("big-ns", workloads)
    assert partition.should_split is True
    assert not any(edge.kind == "shared_configmap" for edge in partition.edges)


def test_shared_pvc_couples_workloads() -> None:
    workloads = (
        _workload("writer", app_group="data", claim_name="shared-data"),
        _workload("reader", app_group="other", claim_name="shared-data"),
        *(_workload(f"web-{i}", app_group="frontend") for i in range(4)),
    )
    partition = propose_namespace_partition("big-ns", workloads)
    assert partition.should_split is True
    data_group = next(
        group
        for group in partition.groups
        if "writer" in group.workload_names or "reader" in group.workload_names
    )
    assert set(data_group.workload_names) >= {"writer", "reader"}


def test_no_split_when_all_groups_communicate(tmp_path: Path) -> None:
    workloads: list[Workload] = []
    for index in range(3):
        path = tmp_path / f"web-{index}.yaml"
        path.write_text(
            """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  template:
    spec:
      containers:
      - name: app
        env:
        - name: API_URL
          value: http://api-0:8080
""",
            encoding="utf-8",
        )
        workloads.append(
            _workload(
                f"web-{index}",
                app_group="frontend",
                labels={"app": f"web-{index}"},
                file_path=str(path),
            )
        )
    workloads.extend(
        _workload(f"api-{i}", app_group="backend", labels={"app": "api"}) for i in range(3)
    )
    services = (
        _service("api-0", {"app": "api"}),
        *(_service(f"web-{i}", {"app": f"web-{i}"}) for i in range(3)),
    )
    partition = propose_namespace_partition("big-ns", tuple(workloads), services)
    assert partition.should_split is False
    assert len(partition.groups) == 1
    assert any(edge.kind == "env_call" for edge in partition.edges)


def test_singleton_app_groups_are_listed_as_namespace_candidates() -> None:
    workloads = tuple(
        _workload(f"app-{i}", app_group=f"app-{i}", labels={"app": f"app-{i}"})
        for i in range(6)
    )
    services = tuple(_service(f"app-{i}", {"app": f"app-{i}"}) for i in range(6))
    routes = tuple(_route(f"app-{i}", f"app-{i}") for i in range(6))
    partition = propose_namespace_partition("big-ns", workloads, services, routes)
    assert partition.should_split is True
    assert len(partition.groups) == 6
    names = {name for group in partition.groups for name in group.workload_names}
    assert names == {wl.name for wl in workloads}


def test_extract_service_calls_from_env(tmp_path: Path) -> None:
    path = tmp_path / "caller.yaml"
    path.write_text(
        """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: caller
spec:
  template:
    spec:
      containers:
      - name: app
        env:
        - name: SVC
          value: http://backend-api.big-ns.svc.cluster.local:8080
""",
        encoding="utf-8",
    )
    workload = _workload("caller", app_group="frontend", file_path=str(path))
    calls = extract_service_calls(workload, {"backend-api", "other"})
    assert calls
    assert calls[0][0] == "backend-api"
    assert calls[0][2] == "SVC"
