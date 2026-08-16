"""Extração de datasets de composição."""

from __future__ import annotations

from collections import Counter

from kubeoptix_analyzer.report.pipeline import AssessmentBundle
from kubeoptix_analyzer.visualization.models import CompositionDataset, PieSlice
from kubeoptix_analyzer.visualization.provenance import calculated


def build_qos_distribution(bundle: AssessmentBundle) -> CompositionDataset | None:
    workloads = bundle.context.workloads
    counts: Counter[str] = Counter()
    for wl in workloads:
        qos = wl.qos_class or "Desconhecido"
        counts[qos] += 1
    if not counts:
        return None
    slices = tuple(
        PieSlice(
            label=label,
            value=float(count),
            provenance=(calculated(f"Contagem de workloads com QoS {label}"),),
        )
        for label, count in sorted(counts.items())
    )
    return CompositionDataset(
        title="Distribuição de QoS",
        question="Como os workloads se distribuem entre classes QoS?",
        slices=slices,
    )


def build_severity_distribution(bundle: AssessmentBundle) -> CompositionDataset | None:
    findings = bundle.analysis.findings
    if not findings:
        return None
    counts: Counter[str] = Counter(f.severity.value for f in findings)
    slices = tuple(
        PieSlice(
            label=severity,
            value=float(count),
            provenance=(calculated(f"Contagem de findings com severidade {severity}"),),
        )
        for severity, count in sorted(counts.items())
    )
    return CompositionDataset(
        title="Findings por severidade",
        question="Qual a distribuição de severidade dos findings?",
        slices=slices,
    )


def build_category_distribution(bundle: AssessmentBundle) -> CompositionDataset | None:
    findings = bundle.analysis.findings
    if not findings:
        return None
    counts: Counter[str] = Counter(f.category for f in findings)
    slices = tuple(
        PieSlice(
            label=category,
            value=float(count),
            provenance=(calculated(f"Contagem de findings na categoria {category}"),),
        )
        for category, count in sorted(counts.items())
    )
    return CompositionDataset(
        title="Findings por categoria",
        question="Quais categorias concentram mais findings?",
        slices=slices,
    )


def build_workloads_by_app_group(bundle: AssessmentBundle) -> CompositionDataset | None:
    workloads = bundle.context.workloads
    if not workloads:
        return None
    counts: Counter[str] = Counter(wl.app_group for wl in workloads)
    if len(counts) <= 1 and len(workloads) <= 1:
        return None
    slices = tuple(
        PieSlice(
            label=group,
            value=float(count),
            provenance=(calculated(f"Contagem de workloads no app group {group}"),),
        )
        for group, count in sorted(counts.items())
    )
    return CompositionDataset(
        title="Workloads por app group",
        question="Como os workloads se distribuem por grupo de aplicação?",
        slices=slices,
    )
