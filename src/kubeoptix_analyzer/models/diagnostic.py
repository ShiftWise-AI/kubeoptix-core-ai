"""Modelos do relatório de diagnóstico de ingestão."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ContainerResourceEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    workload: str
    container: str
    value_raw: str
    field_path: str
    file_path: str


class ResourceTotals(BaseModel):
    """Totais agregados com indicação de disponibilidade."""

    model_config = ConfigDict(frozen=True)

    available: bool
    total_normalized: float | None = None
    display: str
    note: str | None = None
    entries: tuple[ContainerResourceEntry, ...] = ()


class WorkloadDiagnosticSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    workload_count: int
    container_count: int
    replicas_desired_total: int | None
    replicas_unavailable_count: int
    cpu_requests: ResourceTotals
    cpu_limits: ResourceTotals
    memory_requests: ResourceTotals
    memory_limits: ResourceTotals


class WorknodeDiagnosticSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    worknode_count: int
    cpu_capacity: ResourceTotals
    cpu_allocatable: ResourceTotals
    memory_capacity: ResourceTotals
    memory_allocatable: ResourceTotals
    parse_errors: tuple[str, ...] = ()


class IngestionDiagnosticReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    namespace: str
    files_found_count: int
    files_to_process_count: int
    files_processed_count: int
    files_ignored_count: int
    files_ignored: tuple[tuple[str, str], ...] = ()
    parse_errors: tuple[str, ...] = ()
    processed_files: tuple[str, ...] = ()
    workloads: WorkloadDiagnosticSummary
    worknodes: WorknodeDiagnosticSummary
