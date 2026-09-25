"""Estado e progresso de execuções de análise (armazenamento em memória)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

# Marcos locais (0-100) de um namespace, alinhados ao pipeline real.
PCT_START = 0
PCT_IDENTIFIED = 10
PCT_READ_START = 20
PCT_READ_END = 70
PCT_ANALYSIS_END = 80
PCT_MARKDOWN = 90
PCT_COMPLETE = 100


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Visão imutável do estado de uma execução para a API."""

    execution_id: str
    status: ExecutionStatus
    progress: int
    message: str
    processed: int
    total: int
    report: str | None
    error: str | None
    namespaces: tuple[str, ...]
    current_stage: str = ""
    current_file: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "execution_id": self.execution_id,
            "status": str(self.status),
            "progress": self.progress,
            "message": self.message,
            "processed": self.processed,
            "total": self.total,
            "report": self.report,
            "current_stage": self.current_stage,
            "current_file": self.current_file,
            # Aliases matching kubeoptix-analyzer's /analysis/status payload so
            # the dashboard's shared progress extractors work for both flows.
            "phase": self.current_stage,
            "running": self.status
            in {ExecutionStatus.PENDING, ExecutionStatus.RUNNING},
            "files_processed": self.processed,
            "files_total": self.total,
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass
class _ExecutionRecord:
    execution_id: str
    namespaces: tuple[str, ...]
    status: ExecutionStatus = ExecutionStatus.PENDING
    progress: int = 0
    message: str = ""
    processed: int = 0
    total: int = 0
    report: str | None = None
    error: str | None = None
    current_stage: str = ""
    current_file: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def snapshot(self) -> ExecutionSnapshot:
        return ExecutionSnapshot(
            execution_id=self.execution_id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            processed=self.processed,
            total=self.total,
            report=self.report,
            error=self.error,
            namespaces=self.namespaces,
            current_stage=self.current_stage,
            current_file=self.current_file,
        )


def clamp_progress(value: int, *, allow_complete: bool = False) -> int:
    """Garante 0 <= progress <= 100; 100 só quando a execução finaliza."""
    bounded = max(0, min(100, int(value)))
    if bounded >= PCT_COMPLETE and not allow_complete:
        return PCT_COMPLETE - 1
    return bounded


class ExecutionStore:
    """Armazena execuções em memória (adequado a uma única instância)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._executions: dict[str, _ExecutionRecord] = {}

    def create(self, namespaces: list[str]) -> ExecutionSnapshot:
        execution_id = uuid.uuid4().hex
        record = _ExecutionRecord(
            execution_id=execution_id,
            namespaces=tuple(namespaces),
            status=ExecutionStatus.PENDING,
            progress=PCT_START,
            message="Execução iniciada",
        )
        with self._lock:
            self._executions[execution_id] = record
        return record.snapshot()

    def get(self, execution_id: str) -> ExecutionSnapshot | None:
        with self._lock:
            record = self._executions.get(execution_id)
            if record is None:
                return None
            return record.snapshot()

    def update(
        self,
        execution_id: str,
        *,
        status: ExecutionStatus | None = None,
        progress: int | None = None,
        message: str | None = None,
        processed: int | None = None,
        total: int | None = None,
        report: str | None = None,
        error: str | None = None,
        current_stage: str | None = None,
        current_file: str | None = None,
        allow_complete: bool = False,
    ) -> ExecutionSnapshot | None:
        with self._lock:
            record = self._executions.get(execution_id)
            if record is None:
                return None
            if record.status in {ExecutionStatus.COMPLETED, ExecutionStatus.ERROR}:
                return record.snapshot()

            if status is not None:
                record.status = status
            if progress is not None:
                next_progress = clamp_progress(
                    progress, allow_complete=allow_complete
                )
                if next_progress >= record.progress:
                    record.progress = next_progress
            if message is not None:
                record.message = message
            if processed is not None:
                record.processed = max(0, processed)
            if total is not None:
                record.total = max(0, total)
            if report is not None:
                record.report = report
            if error is not None:
                record.error = error
            if current_stage is not None:
                record.current_stage = current_stage
            if current_file is not None:
                record.current_file = current_file
            record.updated_at = datetime.now(tz=UTC)
            return record.snapshot()


class RunProgress:
    """Traduz etapas reais do pipeline em progresso 0-100 por execução."""

    def __init__(
        self,
        store: ExecutionStore,
        execution_id: str,
        namespace_count: int,
    ) -> None:
        self._store = store
        self._execution_id = execution_id
        self._namespace_count = max(1, namespace_count)
        self._ns_index = 0
        self._processed = 0
        self._total = 0
        self._last_report: str | None = None

    def set_running(self) -> None:
        self._publish(
            local_pct=PCT_START,
            status=ExecutionStatus.RUNNING,
            stage="Inicialização",
            message="Execução iniciada",
        )

    def set_total(self, total: int) -> None:
        self._total = max(0, total)
        self._store.update(self._execution_id, total=self._total)

    def begin_namespace(self, index: int, namespace: str) -> None:
        self._ns_index = index
        self._publish(
            local_pct=PCT_START,
            stage="Inicialização",
            message=f"Iniciando análise do namespace {namespace}",
        )

    def yamls_identified(self, count: int) -> None:
        self._publish(
            local_pct=PCT_IDENTIFIED,
            stage="Coleta de dados",
            message="YAMLs identificados",
        )
        if count >= 0 and self._total == 0:
            self._total = count
            self._store.update(self._execution_id, total=self._total)

    def yaml_read_started(self) -> None:
        self._publish(
            local_pct=PCT_READ_START,
            stage="Coleta de dados",
            message="Leitura dos YAMLs iniciada",
        )

    def yaml_file_started(self, file_path: str) -> None:
        self._publish(
            local_pct=PCT_READ_START,
            stage="Coleta de dados",
            current_file=Path(file_path).name,
            message="Processando arquivo",
        )

    def yaml_file_processed(self, processed: int, total: int) -> None:
        self._processed += 1
        if self._processed > self._total:
            self._total = self._processed
        if total <= 0:
            local = PCT_READ_END
        else:
            fraction = min(processed / total, 1.0)
            span = PCT_READ_END - PCT_READ_START
            local = PCT_READ_START + int(fraction * span)
        self._publish(
            local_pct=local,
            stage="Coleta de dados",
            message="Analisando YAMLs",
        )

    def yaml_read_finished(self) -> None:
        self._publish(
            local_pct=PCT_READ_END,
            stage="Coleta de dados",
            message="Leitura dos YAMLs concluída",
        )

    def analysis_step(self, step: int, step_count: int, label: str) -> None:
        if step_count <= 0:
            local = PCT_ANALYSIS_END
        else:
            span = PCT_ANALYSIS_END - PCT_READ_END
            local = PCT_READ_END + int((step / step_count) * span)
        self._publish(
            local_pct=local,
            stage=("Análise preditiva" if label == "ML" else "Análise dos dados"),
            message=f"Analisando objetos ({label})",
        )

    def analysis_finished(self) -> None:
        self._publish(
            local_pct=PCT_ANALYSIS_END,
            stage="Análise dos dados",
            message="Análise dos objetos concluída",
        )

    def markdown_started(self) -> None:
        self._publish(
            local_pct=PCT_MARKDOWN,
            stage="Geração dos resultados",
            message="Geração do relatório Markdown",
        )

    def namespace_report_written(self, report_path: str) -> None:
        self._last_report = report_path
        is_last = self._ns_index >= self._namespace_count - 1
        if is_last:
            return
        self._publish(
            local_pct=PCT_COMPLETE,
            stage="Finalização",
            message="Relatório gerado com sucesso",
            report=report_path,
            allow_complete=False,
        )

    def completed(self, report_path: str | None = None) -> None:
        report = report_path or self._last_report
        if report is not None:
            self._last_report = report
        self._store.update(
            self._execution_id,
            status=ExecutionStatus.COMPLETED,
            progress=PCT_COMPLETE,
            current_stage="Finalização",
            message="Relatório gerado com sucesso",
            processed=self._processed,
            total=self._total,
            report=self._last_report,
            allow_complete=True,
        )

    def failed(self, message: str, error: str) -> None:
        self._store.update(
            self._execution_id,
            status=ExecutionStatus.ERROR,
            message=message,
            error=error,
        )

    def _global_progress(self, local_pct: int, *, allow_complete: bool) -> int:
        span = 100 / self._namespace_count
        raw = self._ns_index * span + (local_pct / 100) * span
        return clamp_progress(int(raw), allow_complete=allow_complete)

    def _publish(
        self,
        *,
        local_pct: int,
        message: str,
        status: ExecutionStatus | None = None,
        stage: str | None = None,
        current_file: str | None = None,
        report: str | None = None,
        allow_complete: bool = False,
    ) -> None:
        self._store.update(
            self._execution_id,
            status=status,
            progress=self._global_progress(local_pct, allow_complete=allow_complete),
            message=message,
            current_stage=stage,
            current_file=current_file,
            processed=self._processed,
            total=self._total,
            report=report,
            allow_complete=allow_complete,
        )
