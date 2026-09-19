"""Testes da API assíncrona de relatórios com progresso."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api
from kubeoptix_core_ai.api.assessment import AssessmentService
from kubeoptix_core_ai.api.progress import ExecutionStore
from kubeoptix_core_ai.errors import AnalyzerError

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_NAMESPACE = "example-ns-prd"
OTHER_NAMESPACE = "other-ns-prd"
POLL_TIMEOUT_SECONDS = 30


@pytest.fixture
def analysis_tree(tmp_path: Path) -> Path:
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


@pytest.fixture
def execution_store(monkeypatch: pytest.MonkeyPatch) -> ExecutionStore:
    store = ExecutionStore()
    monkeypatch.setattr(api, "_get_execution_store", lambda: store)
    return store


@pytest.fixture
def reports_client(
    analysis_tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    execution_store: ExecutionStore,
) -> TestClient:
    reports_dir = tmp_path / "reports"
    service = AssessmentService(
        assessment_dir=analysis_tree,
        reports_dir=reports_dir,
    )
    monkeypatch.setattr(api, "_get_assessment_service", lambda: service)
    with TestClient(api.app) as test_client:
        yield test_client


def _wait_terminal(client: TestClient, execution_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last: dict | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/reports/{execution_id}/status")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in {"completed", "error"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"timeout aguardando execução {execution_id}: {last}")


def test_start_report_returns_immediately_with_pending(
    reports_client: TestClient,
) -> None:
    response = reports_client.post(
        "/api/reports",
        json={"namespaces": [EXAMPLE_NAMESPACE], "enable_ml": False},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["progress"] == 0
    assert body["execution_id"]
    _wait_terminal(reports_client, body["execution_id"])


def test_report_status_polls_until_markdown_exists(
    reports_client: TestClient,
) -> None:
    started = reports_client.post(
        "/api/reports",
        json={"namespaces": [EXAMPLE_NAMESPACE], "enable_ml": False},
    )
    execution_id = started.json()["execution_id"]

    final = _wait_terminal(reports_client, execution_id)

    assert final["execution_id"] == execution_id
    assert final["status"] == "completed"
    assert final["progress"] == 100
    assert final["message"] == "Relatório gerado com sucesso"
    assert final["processed"] >= 1
    assert final["total"] >= final["processed"]
    assert final["report"] is not None
    assert Path(final["report"]).is_file()
    assert final["report"].endswith(f"ml-{EXAMPLE_NAMESPACE}.md")


def test_delete_report_removes_markdown_and_assets(
    reports_client: TestClient,
) -> None:
    reports_dir = api._get_assessment_service().reports_dir
    report = reports_dir / f"ml-{EXAMPLE_NAMESPACE}.md"
    assets = reports_dir / f"ml-{EXAMPLE_NAMESPACE}_assets"
    assets.mkdir(parents=True)
    report.write_text("# report\n", encoding="utf-8")
    (assets / "chart.png").write_bytes(b"png")

    response = reports_client.request(
        "DELETE",
        "/api/reports",
        json={"nome_do_arquivo": report.name},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["report"] == str(report)
    assert body["assets"] == str(assets)
    assert body["deleted_assets"] is True
    assert not report.exists()
    assert not assets.exists()


def test_delete_report_by_path_param_removes_markdown_and_assets(
    reports_client: TestClient,
) -> None:
    reports_dir = api._get_assessment_service().reports_dir
    report = reports_dir / f"ml-{EXAMPLE_NAMESPACE}.md"
    assets = reports_dir / f"ml-{EXAMPLE_NAMESPACE}_assets"
    assets.mkdir(parents=True)
    report.write_text("# report\n", encoding="utf-8")
    (assets / "chart.png").write_bytes(b"png")

    response = reports_client.delete(f"/api/reports/{report.name}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["report"] == str(report)
    assert body["assets"] == str(assets)
    assert body["deleted_assets"] is True
    assert not report.exists()
    assert not assets.exists()


def test_delete_report_by_path_param_without_api_prefix(
    reports_client: TestClient,
) -> None:
    reports_dir = api._get_assessment_service().reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = reports_dir / f"ml-{EXAMPLE_NAMESPACE}.md"
    report.write_text("# report\n", encoding="utf-8")

    response = reports_client.delete(f"/reports/{report.name}")

    assert response.status_code == 200
    assert not report.exists()


def test_delete_report_returns_404_for_missing_markdown(
    reports_client: TestClient,
) -> None:
    response = reports_client.request(
        "DELETE",
        "/api/reports",
        json={"nome_do_arquivo": "missing.md"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["message"] == "Relatório não encontrado."


def test_delete_report_rejects_path_traversal(
    reports_client: TestClient,
) -> None:
    response = reports_client.request(
        "DELETE",
        "/api/reports",
        json={"nome_do_arquivo": "../outside.md"},
    )

    assert response.status_code == 422


def test_report_progress_evolves_during_run(
    reports_client: TestClient,
) -> None:
    started = reports_client.post(
        "/api/reports",
        json={"namespaces": [EXAMPLE_NAMESPACE], "enable_ml": False},
    )
    execution_id = started.json()["execution_id"]

    seen_progress: list[int] = []
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    final = None
    while time.monotonic() < deadline:
        body = reports_client.get(f"/api/reports/{execution_id}/status").json()
        seen_progress.append(body["progress"])
        if body["status"] in {"completed", "error"}:
            final = body
            break
        time.sleep(0.05)

    assert final is not None
    assert final["status"] == "completed"
    assert seen_progress[0] >= 0
    assert seen_progress[-1] == 100
    assert all(0 <= value <= 100 for value in seen_progress)
    assert seen_progress == sorted(seen_progress)


def test_multiple_executions_have_distinct_ids(
    reports_client: TestClient,
) -> None:
    first = reports_client.post(
        "/api/reports",
        json={"namespaces": [EXAMPLE_NAMESPACE], "enable_ml": False},
    )
    second = reports_client.post(
        "/api/reports",
        json={"namespaces": [OTHER_NAMESPACE], "enable_ml": False},
    )

    first_id = first.json()["execution_id"]
    second_id = second.json()["execution_id"]
    assert first_id != second_id

    first_final = _wait_terminal(reports_client, first_id)
    second_final = _wait_terminal(reports_client, second_id)
    assert first_final["status"] == "completed"
    assert second_final["status"] == "completed"
    assert first_final["report"] != second_final["report"]


def test_unknown_execution_returns_404(reports_client: TestClient) -> None:
    response = reports_client.get("/api/reports/does-not-exist/status")

    assert response.status_code == 404
    assert response.json()["detail"]["execution_id"] == "does-not-exist"


def test_start_report_rejects_unknown_namespace(reports_client: TestClient) -> None:
    response = reports_client.post(
        "/api/reports",
        json={"namespaces": ["missing-ns-prd"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["missing_namespaces"] == ["missing-ns-prd"]


def test_report_execution_error_sets_error_status(
    reports_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_run(
        self: AssessmentService,
        namespaces: list[str],
        enable_ml: bool | None = None,
        progress=None,
    ):
        if progress is not None:
            progress.set_running()
            progress.yaml_read_started()
        raise AnalyzerError("Falha simulada")

    monkeypatch.setattr(AssessmentService, "run", _fail_run)

    started = reports_client.post(
        "/api/reports",
        json={"namespaces": [EXAMPLE_NAMESPACE]},
    )
    execution_id = started.json()["execution_id"]
    final = _wait_terminal(reports_client, execution_id)

    assert final["status"] == "error"
    assert final["progress"] < 100
    assert final["error"]
    assert "análise" in final["message"].lower()
