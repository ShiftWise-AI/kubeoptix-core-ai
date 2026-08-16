"""Testes de scoring e estrutura de findings."""

from __future__ import annotations

from kubeoptix_analyzer.analysis.findings_builder import FindingBuilder
from kubeoptix_analyzer.models.finding import Confidence, EvidenceItem, Severity


def test_finding_ids_sequential_per_category() -> None:
    builder = FindingBuilder()
    f1 = builder.add(
        category="CPU",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        namespace="test-ns",
        analysis="teste 1",
        evidence=(EvidenceItem(description="ev1"),),
    )
    f2 = builder.add(
        category="CPU",
        severity=Severity.LOW,
        confidence=Confidence.MEDIUM,
        namespace="test-ns",
        analysis="teste 2",
    )
    f3 = builder.add(
        category="MEM",
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        namespace="test-ns",
        analysis="teste 3",
    )

    assert f1.id == "RES-CPU-001"
    assert f2.id == "RES-CPU-002"
    assert f3.id == "RES-MEM-001"
    assert len(builder.findings) == 3
