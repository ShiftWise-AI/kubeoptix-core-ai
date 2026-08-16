"""Construção de findings com IDs sequenciais."""

from __future__ import annotations

from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Finding, Severity
from kubeoptix_analyzer.models.source import DataSourceRef


class FindingBuilder:
    """Gera findings com IDs únicos por categoria (ex.: RES-CPU-001)."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._findings: list[Finding] = []

    def next_id(self, category: str) -> str:
        self._counters[category] = self._counters.get(category, 0) + 1
        return f"RES-{category}-{self._counters[category]:03d}"

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
            limitation=limitation,
            sources=sources,
        )
        self._findings.append(finding)
        return finding

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(self._findings)

    def extend(self, findings: tuple[Finding, ...]) -> None:
        for finding in findings:
            self._counters[finding.category] = self._counters.get(finding.category, 0) + 1
            # Re-ID to avoid collisions when merging
            renumbered = finding.model_copy(
                update={"id": f"RES-{finding.category}-{self._counters[finding.category]:03d}"}
            )
            self._findings.append(renumbered)
