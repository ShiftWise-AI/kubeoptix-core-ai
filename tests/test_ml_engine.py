"""Testes da camada ML local."""

from __future__ import annotations

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.ml.config import MLConfig
from kubeoptix_core_ai.ml.engine import MLEngine
from kubeoptix_core_ai.ml.features import build_feature_matrix
from kubeoptix_core_ai.models.quantities import ResourceQuantity
from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef
from kubeoptix_core_ai.models.workload import ContainerSpec, NamespaceWorkloadBundle, Workload
from kubeoptix_core_ai.normalize.workload import enrich_workload

_SRC = DataSourceRef(
    file_path="/tmp/deploy.yaml",
    resource_kind="Deployment",
    resource_name="test",
    namespace="ns-test",
)


def _field(path: str, raw: str) -> FieldRef:
    return FieldRef(file_path=_SRC.file_path, field_path=path, raw_value=raw)


def _cpu(millicores: float) -> ResourceQuantity:
    return ResourceQuantity(
        raw=f"{int(millicores)}m",
        resource_kind="cpu",
        normalized_value=millicores,
        display_unit="m",
        source=_field("cpu", f"{int(millicores)}m"),
    )


def _mem(mib: int) -> ResourceQuantity:
    bytes_val = mib * 1024**2
    return ResourceQuantity(
        raw=f"{mib}Mi",
        resource_kind="memory",
        normalized_value=float(bytes_val),
        display_unit="Mi",
        source=_field("memory", f"{mib}Mi"),
    )


def _container(
    name: str,
    *,
    cpu_req: int = 100,
    mem_req: int = 128,
    cpu_lim: int | None = None,
    mem_lim: int | None = None,
) -> ContainerSpec:
    return ContainerSpec(
        name=name,
        cpu_request=_cpu(cpu_req),
        cpu_limit=_cpu(cpu_lim or cpu_req * 2),
        memory_request=_mem(mem_req),
        memory_limit=_mem(mem_lim or mem_req * 2),
        source=_SRC,
    )


def _workload(
    name: str,
    *,
    replicas: int = 2,
    cpu_req: int = 100,
    mem_req: int = 128,
) -> Workload:
    wl = Workload(
        namespace="ns-test",
        name=name,
        app_group=name,
        kind="Deployment",
        replicas_desired=replicas,
        containers=(_container(name, cpu_req=cpu_req, mem_req=mem_req),),
        source=_SRC,
    )
    return enrich_workload(wl)


def _bundle(*workloads: Workload) -> NamespaceWorkloadBundle:
    return NamespaceWorkloadBundle(namespace="ns-test", workloads=workloads)


def test_feature_matrix_shape() -> None:
    workloads = (_workload("a"), _workload("b", cpu_req=500), _workload("c", cpu_req=50))
    matrix = build_feature_matrix(workloads)
    assert matrix.workload_count == 3
    assert matrix.matrix.shape == (3, 14)


def test_ml_engine_produces_findings_with_enough_workloads() -> None:
    workloads = (
        _workload("api-small", cpu_req=100, mem_req=128, replicas=2),
        _workload("api-medium", cpu_req=200, mem_req=256, replicas=2),
        _workload("batch-heavy", cpu_req=4000, mem_req=4096, replicas=1),
        _workload("worker", cpu_req=300, mem_req=512, replicas=3),
        _workload("cache", cpu_req=150, mem_req=256, replicas=2),
    )
    ctx = AnalysisContext(bundle=_bundle(*workloads), nodes=())
    engine = MLEngine(MLConfig(random_seed=42))
    findings, _ = engine.analyze(ctx)

    assert findings
    assert all(f.id.startswith("ML-") for f in findings)
    categories = {f.category for f in findings}
    assert "MLSTAT" in categories or "MLCOMP" in categories


def test_ml_engine_reproducible_with_same_seed() -> None:
    workloads = tuple(_workload(f"w{i}", cpu_req=100 + i * 50) for i in range(5))
    ctx = AnalysisContext(bundle=_bundle(*workloads), nodes=())

    run_a = MLEngine(MLConfig(random_seed=99)).analyze(ctx)[0]
    run_b = MLEngine(MLConfig(random_seed=99)).analyze(ctx)[0]

    assert [f.id for f in run_a] == [f.id for f in run_b]
    assert [f.analysis for f in run_a] == [f.analysis for f in run_b]


def test_ml_engine_skipped_for_single_workload() -> None:
    ctx = AnalysisContext(bundle=_bundle(_workload("only")), nodes=())
    findings, limits = MLEngine().analyze(ctx)
    assert not findings
    assert any("Menos de 2 workloads" in lim for lim in limits)


def test_outlier_workload_has_stat_or_anom_finding() -> None:
    workloads = (
        _workload("normal-1", cpu_req=200),
        _workload("normal-2", cpu_req=220),
        _workload("normal-3", cpu_req=210),
        _workload("normal-4", cpu_req=190),
        _workload("outlier", cpu_req=8000),
    )
    ctx = AnalysisContext(bundle=_bundle(*workloads), nodes=())
    findings, _ = MLEngine(MLConfig(random_seed=7)).analyze(ctx)
    outlier_findings = [f for f in findings if f.workload == "outlier"]
    assert outlier_findings
    assert any(f.category in ("MLSTAT", "MLANOM", "MLCOMP") for f in outlier_findings)


def test_similar_workloads_reported() -> None:
    workloads = (
        _workload("svc-a", cpu_req=500, mem_req=512, replicas=2),
        _workload("svc-b", cpu_req=505, mem_req=520, replicas=2),
        _workload("svc-c", cpu_req=100, mem_req=128, replicas=1),
    )
    ctx = AnalysisContext(bundle=_bundle(*workloads), nodes=())
    findings, _ = MLEngine(MLConfig(similarity_threshold=0.95, random_seed=1)).analyze(ctx)
    sim = [f for f in findings if f.category == "MLSIM"]
    assert sim
    assert any("svc-a" in f.analysis and "svc-b" in f.analysis for f in sim)
