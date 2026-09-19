"""Testes do serviço de análise da API."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.api.assessment import (
    AssessmentService,
    NamespaceNotFoundError,
    build_report_filename,
    dedupe_namespaces,
)
from kubeoptix_core_ai.api.progress import ExecutionStore, RunProgress
from kubeoptix_core_ai.errors import ConfigurationError

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_NAMESPACE = "example-ns-prd"
OTHER_NAMESPACE = "other-ns-prd"


@pytest.fixture
def analysis_tree(tmp_path: Path) -> Path:
    """Monta diretório de assessment com dois namespaces e worknodes."""
    base = tmp_path / "assessment"
    for namespace in (EXAMPLE_NAMESPACE, OTHER_NAMESPACE):
        ns = base / namespace
        app = ns / "apps" / "backend-acesso-app"
        (app / "deployments").mkdir(parents=True)
        shutil.copy(
            FIXTURES / "deployment_backend_acesso_app.yaml",
            app / "deployments" / "backend-acesso-app.yaml",
        )
        pods = ns / "resources" / "pods"
        pods.mkdir(parents=True)
        shutil.copy(FIXTURES / "pod_backend_acesso_app.yaml", pods / "pod.yaml")
        metrics = ns / "resources" / "pods.metrics.k8s.io"
        metrics.mkdir(parents=True)
        shutil.copy(FIXTURES / "pod_metrics_backend_acesso_app.yaml", metrics / "m.yaml")

    nodes = base / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")
    return base


def test_dedupe_namespaces_preserves_order() -> None:
    assert dedupe_namespaces(["a", "b", "a", "c"]) == ["a", "b", "c"]


def test_build_report_filename() -> None:
    assert build_report_filename("example-ns-prd") == "ml-example-ns-prd.md"


def test_assessment_service_rejects_missing_namespace(
    analysis_tree: Path,
    tmp_path: Path,
) -> None:
    service = AssessmentService(
        assessment_dir=analysis_tree,
        reports_dir=tmp_path / "reports",
    )

    with pytest.raises(NamespaceNotFoundError) as exc_info:
        service.validate_namespaces(["missing-ns-prd"])

    assert exc_info.value.missing == ["missing-ns-prd"]


def test_assessment_service_rejects_invalid_namespace_name(
    analysis_tree: Path,
    tmp_path: Path,
) -> None:
    service = AssessmentService(
        assessment_dir=analysis_tree,
        reports_dir=tmp_path / "reports",
    )

    with pytest.raises(ConfigurationError):
        service.validate_namespaces(["INVALID_NAMESPACE"])


def test_assessment_service_run_single_namespace(
    analysis_tree: Path,
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    service = AssessmentService(
        assessment_dir=analysis_tree,
        reports_dir=reports_dir,
    )

    result = service.run([EXAMPLE_NAMESPACE], enable_ml=False)

    assert result.status == "SUCCESS"
    assert len(result.reports) == 1
    report = result.reports[0]
    assert report.namespace == EXAMPLE_NAMESPACE
    assert report.report_path.parent == reports_dir
    assert report.report_path.is_file()
    assert report.workloads_analyzed >= 1
    assert report.finding_count > 0
    assert report.report_path.name == f"ml-{EXAMPLE_NAMESPACE}.md"
    assert report.report_path.read_text(encoding="utf-8").startswith("---")


def test_assessment_service_run_reports_progress_until_markdown_exists(
    analysis_tree: Path,
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    service = AssessmentService(
        assessment_dir=analysis_tree,
        reports_dir=reports_dir,
    )
    store = ExecutionStore()
    snapshot = store.create([EXAMPLE_NAMESPACE])
    progress = RunProgress(store, snapshot.execution_id, 1)

    result = service.run([EXAMPLE_NAMESPACE], enable_ml=False, progress=progress)

    assert result.status == "SUCCESS"
    done = store.get(snapshot.execution_id)
    assert done is not None
    assert done.status.value == "completed"
    assert done.progress == 100
    assert done.report is not None
    assert Path(done.report).is_file()
    assert done.processed >= 1
    assert done.total >= done.processed


def test_assessment_service_run_multiple_namespaces(
    analysis_tree: Path,
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    service = AssessmentService(
        assessment_dir=analysis_tree,
        reports_dir=reports_dir,
    )

    result = service.run([EXAMPLE_NAMESPACE, OTHER_NAMESPACE], enable_ml=False)

    assert result.status == "SUCCESS"
    assert len(result.reports) == 2
    namespaces = {item.namespace for item in result.reports}
    assert namespaces == {EXAMPLE_NAMESPACE, OTHER_NAMESPACE}
    for item in result.reports:
        assert item.report_path.is_file()
        assert item.report_path.name == f"ml-{item.namespace}.md"
