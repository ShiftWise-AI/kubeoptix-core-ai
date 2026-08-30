"""API REST FastAPI para health checks e operação em OpenShift."""

from __future__ import annotations

import json
import logging
import os
import signal
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from kubeoptix_core_ai.api.assessment import (
    AssessmentService,
    NamespaceNotFoundError,
    dedupe_namespaces,
)
from kubeoptix_core_ai.api.progress import (
    ExecutionStore,
    RunProgress,
)
from kubeoptix_core_ai.errors import AnalyzerError, ConfigurationError
from kubeoptix_core_ai.visualization.pipeline import report_assets_prefix

DEFAULT_PORT = 8000
APP_NAME = "kubeoptix-core-ai"
MARK_DOWN_FILE_ENV = "MARK_DOWN_FILE"
TMP_DIR = Path("/tmp")

_start_monotonic: float = time.monotonic()
_app_initialized: bool = False
_execution_store = ExecutionStore()
_report_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="kubeoptix-report",
)


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


class AnalysisRequest(BaseModel):
    """Corpo da requisição para análise de um ou mais namespaces."""

    namespaces: list[str] = Field(
        ...,
        min_length=1,
        description="Lista com um ou mais namespaces a analisar.",
        examples=[["example-ns-prd"], ["example-ns-prd", "other-ns-prd"]],
    )
    enable_ml: bool | None = Field(
        default=None,
        description=(
            "Ativa ou desativa a camada ML local. "
            "Quando omitido, usa a configuração de ambiente."
        ),
    )

    @field_validator("namespaces")
    @classmethod
    def validate_namespace_entries(cls, namespaces: list[str]) -> list[str]:
        cleaned: list[str] = []
        for namespace in namespaces:
            if not namespace or not namespace.strip():
                raise ValueError("Cada namespace deve ser uma string não vazia.")
            cleaned.append(namespace.strip())
        return cleaned


class NamespaceReportResponse(BaseModel):
    namespace: str
    report_path: str
    workloads_analyzed: int = Field(ge=0)
    finding_count: int = Field(ge=0)


class AnalysisResponse(BaseModel):
    """Resultado da análise com caminhos dos relatórios Markdown gerados."""

    status: str
    reports: list[NamespaceReportResponse]


class ReportAcceptedResponse(BaseModel):
    """Resposta imediata ao iniciar geração assíncrona de relatório."""

    execution_id: str
    status: str
    progress: int = Field(ge=0, le=100)


class ReportStatusResponse(BaseModel):
    """Estado de uma execução de análise para polling do frontend."""

    execution_id: str
    status: str
    progress: int = Field(ge=0, le=100)
    message: str = ""
    processed: int = Field(ge=0, default=0)
    total: int = Field(ge=0, default=0)
    report: str | None = None
    error: str | None = None


class DeleteReportRequest(BaseModel):
    """Corpo da requisição para apagar um relatório gerado."""

    nome_do_arquivo: str = Field(
        ...,
        description="Nome do arquivo Markdown gerado em /app/data/reports.",
        examples=["example-ns-prd.md"],
    )

    @field_validator("nome_do_arquivo")
    @classmethod
    def validate_markdown_filename(cls, value: str) -> str:
        filename = value.strip()
        path = Path(filename)
        if not filename or path.name != filename or path.suffix.lower() != ".md":
            raise ValueError("Informe apenas o nome de um arquivo .md.")
        if not path.stem:
            raise ValueError("Informe um nome de arquivo .md válido.")
        return filename


class DeleteReportResponse(BaseModel):
    status: str
    report: str
    assets: str
    deleted_assets: bool


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


def _get_assessment_service() -> AssessmentService:
    return AssessmentService()


def _get_execution_store() -> ExecutionStore:
    return _execution_store


def _get_report_executor() -> ThreadPoolExecutor:
    return _report_executor


def _validate_report_filename(filename: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Informe apenas o nome de um arquivo .md."},
        )
    path = Path(cleaned)
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned or path.name != cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Nome de arquivo inválido."},
        )
    if not cleaned.lower().endswith(".md"):
        cleaned = f"{cleaned}.md"
    return cleaned


def _delete_generated_report(filename: str) -> DeleteReportResponse:
    validated_filename = _validate_report_filename(filename)
    service = _get_assessment_service()
    reports_dir = service.reports_dir
    report_path = (reports_dir / validated_filename).resolve()
    if report_path.parent != reports_dir:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Nome de arquivo inválido."},
        )
    if not report_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Relatório não encontrado.", "report": str(report_path)},
        )

    assets_path = reports_dir / report_assets_prefix(report_path.stem)
    if assets_path.exists() and not assets_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Caminho de assets não é um diretório."},
        )

    report_path.unlink()
    deleted_assets = False
    if assets_path.is_dir():
        shutil.rmtree(assets_path)
        deleted_assets = True

    return DeleteReportResponse(
        status="SUCCESS",
        report=str(report_path),
        assets=str(assets_path),
        deleted_assets=deleted_assets,
    )


def _run_report_execution(
    execution_id: str,
    namespaces: list[str],
    enable_ml: bool | None,
) -> None:
    store = _get_execution_store()
    service = _get_assessment_service()
    progress = RunProgress(store, execution_id, len(namespaces))
    try:
        service.run(namespaces, enable_ml=enable_ml, progress=progress)
    except Exception as exc:
        logger.exception(
            "Falha na execução assíncrona do relatório",
            extra={"execution_id": execution_id, "namespaces": namespaces},
        )
        progress.failed("Erro durante a análise dos YAMLs", str(exc))


@app.post(
    "/analysis",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Executar análise de namespaces",
    response_description="Análise concluída com relatórios Markdown gerados.",
)
async def run_analysis(request: AnalysisRequest) -> AnalysisResponse:
    """
    Executa a análise de um ou mais namespaces e gera relatórios Markdown.

    Os dados de workloads e worknodes são lidos de `/app/data/assessment`
    (ou `KUBEOPTIX_METADATA_DIR`). Os relatórios são gravados em
    `/app/data/reports` (ou `KUBEOPTIX_OUTPUT_DIR`).

    **Exemplo de requisição (um namespace):**

    ```json
    {
      "namespaces": ["example-ns-prd"]
    }
    ```

    **Exemplo de requisição (múltiplos namespaces):**

    ```json
    {
      "namespaces": ["example-ns-prd", "other-ns-prd"],
      "enable_ml": false
    }
    ```

    **Exemplo de resposta (201 Created):**

    ```json
    {
      "status": "SUCCESS",
      "reports": [
        {
          "namespace": "example-ns-prd",
          "report_path": "/app/data/reports/example-ns-prd.md",
          "workloads_analyzed": 3,
          "finding_count": 12
        }
      ]
    }
    ```
    """
    service = _get_assessment_service()
    try:
        result = service.run(
            request.namespaces,
            enable_ml=request.enable_ml,
        )
    except NamespaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": str(exc),
                "missing_namespaces": exc.missing,
            },
        ) from exc
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc)},
        ) from exc
    except AnalyzerError as exc:
        logger.exception(
            "Falha na análise de namespaces",
            extra={"namespaces": request.namespaces},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": str(exc)},
        ) from exc

    return AnalysisResponse(
        status=result.status,
        reports=[
            NamespaceReportResponse(
                namespace=report.namespace,
                report_path=str(report.report_path),
                workloads_analyzed=report.workloads_analyzed,
                finding_count=report.finding_count,
            )
            for report in result.reports
        ],
    )


@app.post(
    "/api/reports",
    response_model=ReportAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Iniciar geração assíncrona de relatórios",
    response_description="Execução aceita; consultar o status pelo execution_id.",
)
@app.post(
    "/reports",
    response_model=ReportAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def start_report(request: AnalysisRequest) -> ReportAcceptedResponse:
    """
    Inicia a análise em background e devolve um `execution_id` imediatamente.

    Consulte `GET /api/reports/{execution_id}/status` para acompanhar o
    progresso (0 a 100) até a geração do Markdown.
    """
    ordered = dedupe_namespaces(request.namespaces)
    service = _get_assessment_service()
    try:
        service.validate_namespaces(ordered)
    except NamespaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": str(exc),
                "missing_namespaces": exc.missing,
            },
        ) from exc
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc)},
        ) from exc

    store = _get_execution_store()
    snapshot = store.create(ordered)
    _get_report_executor().submit(
        _run_report_execution,
        snapshot.execution_id,
        ordered,
        request.enable_ml,
    )
    return ReportAcceptedResponse(
        execution_id=snapshot.execution_id,
        status=str(snapshot.status),
        progress=snapshot.progress,
    )


@app.get(
    "/api/reports/{execution_id}/status",
    response_model=ReportStatusResponse,
    summary="Consultar progresso da geração do relatório",
    response_description="Estado atual da execução (polling).",
)
@app.get(
    "/reports/{execution_id}/status",
    response_model=ReportStatusResponse,
    include_in_schema=False,
)
async def report_status(execution_id: str) -> ReportStatusResponse:
    snapshot = _get_execution_store().get(execution_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Execução não encontrada",
                "execution_id": execution_id,
            },
        )
    return ReportStatusResponse(
        execution_id=snapshot.execution_id,
        status=str(snapshot.status),
        progress=snapshot.progress,
        message=snapshot.message,
        processed=snapshot.processed,
        total=snapshot.total,
        report=snapshot.report,
        error=snapshot.error,
    )


@app.delete(
    "/api/reports/{filename}",
    response_model=DeleteReportResponse,
    summary="Apagar relatório Markdown gerado por nome no path",
    response_description="Relatório Markdown e pasta de assets removidos.",
)
@app.delete(
    "/reports/{filename}",
    response_model=DeleteReportResponse,
    include_in_schema=False,
)
async def delete_report_by_path(filename: str) -> DeleteReportResponse:
    """
    Remove um arquivo Markdown gerado e a pasta `<nome>_assets` correspondente pelo nome no path.
    """
    return _delete_generated_report(filename)


@app.delete(
    "/api/reports",
    response_model=DeleteReportResponse,
    summary="Apagar relatório Markdown gerado",
    response_description="Relatório Markdown e pasta de assets removidos.",
)
@app.delete(
    "/reports",
    response_model=DeleteReportResponse,
    include_in_schema=False,
)
async def delete_report(request: DeleteReportRequest) -> DeleteReportResponse:
    """
    Remove um arquivo Markdown gerado e a pasta `<nome>_assets` correspondente.
    """
    return _delete_generated_report(request.nome_do_arquivo)


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
