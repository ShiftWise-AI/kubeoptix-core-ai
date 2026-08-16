"""Construção de findings da camada ML (IDs prefixados com ML-)."""

from __future__ import annotations

from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Finding, Severity
from kubeoptix_analyzer.models.source import DataSourceRef

_ML_LIMITATION = (
    "Inferência estatística / ML local sobre o namespace analisado. "
    "Outlier estatístico não implica defeito operacional; use como sinal "
    "para investigação complementar às regras determinísticas."
)


class MLFindingBuilder:
    """Gera findings com IDs ML-<CATEGORIA>-NNN."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._findings: list[Finding] = []

    def next_id(self, category: str) -> str:
        self._counters[category] = self._counters.get(category, 0) + 1
        return f"ML-{category}-{self._counters[category]:03d}"

    def add(
        self,
        *,
        category: str,
        severity: Severity,
        confidence: Confidence,
        namespace: str,
        analysis: str,
        workload: str | None = None,
        container: str | None = None,
        evidence: tuple[EvidenceItem, ...] = (),
        impact: str | None = None,
        recommendation: str | None = None,
        limitation: str | None = None,
        sources: tuple[DataSourceRef, ...] = (),
    ) -> Finding:
        finding = Finding(
            id=self.next_id(category),
            category=category,
            severity=severity,
            confidence=confidence,
            namespace=namespace,
            workload=workload,
            container=container,
            evidence=evidence,
            analysis=analysis,
            impact=impact,
            recommendation=recommendation,
            limitation=limitation or _ML_LIMITATION,
            sources=sources,
        )
        self._findings.append(finding)
        return finding

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(self._findings)
