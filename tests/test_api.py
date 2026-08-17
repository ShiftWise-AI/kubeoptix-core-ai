"""Testes da API REST FastAPI."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import signal
import pytest
from fastapi.testclient import TestClient

import api
from kubeoptix_core_ai.api.assessment import AssessmentService
from kubeoptix_core_ai.errors import AnalyzerError

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_NAMESPACE = "example-ns-prd"
OTHER_NAMESPACE = "other-ns-prd"


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
def client() -> TestClient:
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture
def assessment_client(
    client: TestClient,
    analysis_tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    reports_dir = tmp_path / "reports"
    service = AssessmentService(
        assessment_dir=analysis_tree,
        reports_dir=reports_dir,
    )
    monkeypatch.setattr(api, "_get_assessment_service", lambda: service)
    return client


def test_liveness_returns_up(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "UP", "check": "liveness"}


def test_readiness_returns_up_when_checks_pass(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UP"
    assert body["check"] == "readiness"
    assert all(check["status"] == "UP" for check in body["checks"])


def test_readiness_returns_503_when_tmp_not_writable(client: TestClient) -> None:
    with patch("api._check_tmp_writable", return_value=api.ReadinessCheck(
        name="tmp_writable",
        status="DOWN",
        detail="permission denied",
    )):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "DOWN"


def test_readiness_returns_503_when_app_not_initialized(client: TestClient) -> None:
    with patch("api._app_initialized", False):
        response = client.get("/health/ready")

    assert response.status_code == 503
    checks = {item["name"]: item for item in response.json()["checks"]}
    assert checks["app_initialized"]["status"] == "DOWN"


def test_health_returns_version_timestamp_and_uptime(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UP"
    assert body["version"] == api.APP_VERSION
    assert "timestamp" in body
    assert body["uptime_seconds"] >= 0
    assert "mark_down_file" in body


def test_readiness_includes_mark_down_file_check(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "data"
    report_dir.mkdir()
    report_path = report_dir / "report.md"
    monkeypatch.setenv(api.MARK_DOWN_FILE_ENV, str(report_path))

    response = client.get("/health/ready")

    assert response.status_code == 200
    checks = {item["name"]: item for item in response.json()["checks"]}
    assert checks["mark_down_file"]["status"] == "UP"


def test_sigterm_handler_requests_server_shutdown() -> None:
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(api.app, host="127.0.0.1", port=18000, log_config=None)
    )
    server.should_exit = False

    def _capture_shutdown(signum: int, frame: object | None = None) -> None:
        server.should_exit = True

    previous_handler = signal.signal(signal.SIGTERM, _capture_shutdown)
    try:
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)
        assert server.should_exit is True
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


def test_global_exception_handler_returns_500() -> None:
    from starlette.requests import Request

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/boom",
        "raw_path": b"/boom",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
    }
    request = Request(scope)

    import asyncio

    response = asyncio.run(
        api.unhandled_exception_handler(request, RuntimeError("boom")),
    )

    assert response.status_code == 500
    assert response.body == b'{"status":"ERROR","message":"Erro interno do servidor","path":"/boom"}'


def test_analysis_requires_namespaces(assessment_client: TestClient) -> None:
    response = assessment_client.post("/analysis", json={})

    assert response.status_code == 422


def test_analysis_rejects_empty_namespaces_list(assessment_client: TestClient) -> None:
    response = assessment_client.post("/analysis", json={"namespaces": []})

    assert response.status_code == 422


def test_analysis_rejects_blank_namespace(assessment_client: TestClient) -> None:
    response = assessment_client.post("/analysis", json={"namespaces": ["  "]})

    assert response.status_code == 422


def test_analysis_returns_404_for_unknown_namespace(assessment_client: TestClient) -> None:
    response = assessment_client.post(
        "/analysis",
        json={"namespaces": ["missing-ns-prd"]},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["missing_namespaces"] == ["missing-ns-prd"]


def test_analysis_single_namespace_success(assessment_client: TestClient) -> None:
    response = assessment_client.post(
        "/analysis",
        json={"namespaces": [EXAMPLE_NAMESPACE], "enable_ml": False},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert len(body["reports"]) == 1
    report = body["reports"][0]
    assert report["namespace"] == EXAMPLE_NAMESPACE
    assert report["workloads_analyzed"] >= 1
    assert report["finding_count"] > 0
    assert Path(report["report_path"]).is_file()
    assert EXAMPLE_NAMESPACE in report["report_path"]


def test_analysis_multiple_namespaces_success(assessment_client: TestClient) -> None:
    response = assessment_client.post(
        "/analysis",
        json={"namespaces": [EXAMPLE_NAMESPACE, OTHER_NAMESPACE], "enable_ml": False},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert len(body["reports"]) == 2
    namespaces = {item["namespace"] for item in body["reports"]}
    assert namespaces == {EXAMPLE_NAMESPACE, OTHER_NAMESPACE}
    for item in body["reports"]:
        assert Path(item["report_path"]).is_file()


def test_analysis_returns_400_for_invalid_namespace_name(
    assessment_client: TestClient,
) -> None:
    response = assessment_client.post(
        "/analysis",
        json={"namespaces": ["INVALID_NAMESPACE"]},
    )

    assert response.status_code == 400
    assert "inválido" in response.json()["detail"]["message"].lower()


def test_analysis_returns_500_on_internal_failure(
    assessment_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_run(self: AssessmentService, namespaces: list[str], enable_ml: bool | None = None):
        raise AnalyzerError("Falha simulada")

    monkeypatch.setattr(AssessmentService, "run", _fail_run)

    response = assessment_client.post(
        "/analysis",
        json={"namespaces": [EXAMPLE_NAMESPACE]},
    )

    assert response.status_code == 500
    assert "Falha simulada" in response.json()["detail"]["message"]
