"""API REST FastAPI para health checks e operação em OpenShift."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DEFAULT_PORT = 8000
APP_NAME = "kubeoptix-core-ai"
MARK_DOWN_FILE_ENV = "MARK_DOWN_FILE"
TMP_DIR = Path("/tmp")

_start_monotonic: float = time.monotonic()
_app_initialized: bool = False


def _resolve_app_version() -> str:
    try:
        return version(APP_NAME)
    except PackageNotFoundError:
        return os.getenv("APP_VERSION", "0.0.0-dev")


APP_VERSION = _resolve_app_version()


class JsonLogFormatter(logging.Formatter):
    """Formata registros de log como JSON para stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


configure_logging()
logger = logging.getLogger(__name__)


class LivenessResponse(BaseModel):
    status: str
    check: str


class ReadinessCheck(BaseModel):
    name: str
    status: str
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    check: str
    checks: list[ReadinessCheck]


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    uptime_seconds: float = Field(ge=0)
    mark_down_file: str | None = None


def _uptime_seconds() -> float:
    return round(time.monotonic() - _start_monotonic, 3)


def _check_tmp_writable() -> ReadinessCheck:
    probe_file = TMP_DIR / ".write_probe"
    try:
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        return ReadinessCheck(name="tmp_writable", status="UP")
    except OSError as exc:
        return ReadinessCheck(
            name="tmp_writable",
            status="DOWN",
            detail=str(exc),
        )


def _check_working_directory() -> ReadinessCheck:
    cwd = Path.cwd()
    if cwd.is_dir():
        return ReadinessCheck(name="working_directory", status="UP", detail=str(cwd))
    return ReadinessCheck(
        name="working_directory",
        status="DOWN",
        detail=f"Diretório inexistente: {cwd}",
    )


def _resolve_mark_down_file() -> Path | None:
    raw = os.getenv(MARK_DOWN_FILE_ENV, "").strip()
    if not raw:
        return None
    return Path(raw)


def _check_mark_down_file() -> ReadinessCheck:
    path = _resolve_mark_down_file()
    if path is None:
        return ReadinessCheck(
            name="mark_down_file",
            status="UP",
            detail="variável não configurada",
        )

    if path.is_file() and os.access(path, os.R_OK):
        return ReadinessCheck(name="mark_down_file", status="UP", detail=str(path))

    parent = path.parent
    if parent.is_dir() and os.access(parent, os.W_OK):
        return ReadinessCheck(
            name="mark_down_file",
            status="UP",
            detail=f"aguardando arquivo em {path}",
        )

    return ReadinessCheck(
        name="mark_down_file",
        status="DOWN",
        detail=f"caminho indisponível: {path}",
    )


def _check_app_initialized() -> ReadinessCheck:
    if _app_initialized:
        return ReadinessCheck(name="app_initialized", status="UP")
    return ReadinessCheck(
        name="app_initialized",
        status="DOWN",
        detail="Aplicação ainda não concluiu a inicialização",
    )


def _run_readiness_checks() -> list[ReadinessCheck]:
    return [
        _check_app_initialized(),
        _check_tmp_writable(),
        _check_working_directory(),
        _check_mark_down_file(),
    ]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _app_initialized
    logger.info(
        "Iniciando aplicação",
        extra={
            "event": "startup",
            "version": APP_VERSION,
            "port": _resolve_port(),
            "mark_down_file": str(_resolve_mark_down_file() or ""),
        },
    )
    _app_initialized = True
    yield
    _app_initialized = False
    logger.info("Encerrando aplicação", extra={"event": "shutdown"})


def _resolve_port() -> int:
    raw_port = os.getenv("PORT", str(DEFAULT_PORT))
    try:
        return int(raw_port)
    except ValueError:
        logger.warning("PORT inválida (%s); usando %s", raw_port, DEFAULT_PORT)
        return DEFAULT_PORT


app = FastAPI(
    title="KubeOptix Core AI API",
    version=APP_VERSION,
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Exceção não tratada",
        extra={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "ERROR",
            "message": "Erro interno do servidor",
            "path": request.url.path,
        },
    )


@app.get("/health/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="UP", check="liveness")


@app.get("/health/ready", response_model=ReadinessResponse)
async def readiness() -> JSONResponse:
    checks = _run_readiness_checks()
    all_up = all(check.status == "UP" for check in checks)
    body = ReadinessResponse(
        status="UP" if all_up else "DOWN",
        check="readiness",
        checks=checks,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_up else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body.model_dump(),
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="UP",
        timestamp=datetime.now(tz=UTC).isoformat(),
        version=APP_VERSION,
        uptime_seconds=_uptime_seconds(),
        mark_down_file=str(_resolve_mark_down_file()) if _resolve_mark_down_file() else None,
    )


def main() -> None:
    import uvicorn

    host = os.getenv("KUBEOPTIX_API_HOST", "0.0.0.0")
    port = _resolve_port()
    graceful_timeout = int(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "30"))

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
        timeout_graceful_shutdown=graceful_timeout,
    )
    server = uvicorn.Server(config)

    def _request_shutdown(signum: int, frame: object | None = None) -> None:
        signal_name = signal.Signals(signum).name
        logger.info(
            "Sinal de encerramento recebido",
            extra={"event": "shutdown_signal", "signal": signal_name},
        )
        server.should_exit = True

    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    logger.info(
        "Servidor HTTP iniciado",
        extra={"event": "server_start", "host": host, "port": port},
    )
    server.run()


if __name__ == "__main__":
    main()
