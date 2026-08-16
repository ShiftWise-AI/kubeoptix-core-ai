"""Modelo de findings de análise."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from kubeoptix_analyzer.models.source import DataSourceRef


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    field_path: str | None = None
    value: str | None = None
    file_path: str | None = None
    container: str | None = None


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    category: str
    severity: Severity
    confidence: Confidence
    namespace: str
    workload: str | None = None
    container: str | None = None
    evidence: tuple[EvidenceItem, ...] = ()
    analysis: str
    impact: str | None = None
    recommendation: str | None = None
    limitation: str | None = None
    sources: tuple[DataSourceRef, ...] = ()


class AnalysisReport(BaseModel):
    """Resultado consolidado da análise de um namespace."""

    namespace: str
    findings: tuple[Finding, ...] = ()
    limitations: tuple[str, ...] = ()
    workloads_analyzed: int = 0
    worknodes_considered: int = 0
    ml_enabled: bool = False

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    def by_category(self, category: str) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.category == category)

    def by_severity(self, severity: Severity) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == severity)
