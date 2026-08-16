"""Testes da API REST FastAPI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import signal
import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture
def client() -> TestClient:
    with TestClient(api.app) as test_client:
        yield test_client


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
