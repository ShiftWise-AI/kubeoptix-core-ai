"""Agrupamento de findings RES-* equivalentes para leitura humana."""

from __future__ import annotations

import re
from collections.abc import Sequence

from kubeoptix_core_ai.analysis.report import format_finding
from kubeoptix_core_ai.models.finding import Finding, Severity

_NUMERIC_RE = re.compile(r"\d+(?:\.\d+)?")
_QUOTED_RE = re.compile(r"`[^`]+`")


def _normalize_analysis(text: str) -> str:
    """Remove valores e nomes específicos para comparar o padrão do achado."""
    normalized = _QUOTED_RE.sub("`<valor>`", text)
    normalized = _NUMERIC_RE.sub("<n>", normalized)
    return normalized


def res_finding_group_key(finding: Finding) -> tuple[object, ...]:
    """Chave de equivalência para findings RES-* (ignora workload e valores numéricos)."""
    return (
        finding.category,
        finding.severity,
        finding.confidence,
        finding.recommendation,
        finding.impact,
        finding.limitation,
        _normalize_analysis(finding.analysis),
    )


def group_identical_res_findings(
    findings: Sequence[Finding],
) -> list[tuple[Finding, ...]]:
    """Agrupa findings RES-* equivalentes, preservando a ordem da primeira ocorrência."""
    key_to_members: dict[tuple[object, ...], list[Finding]] = {}
    for finding in findings:
        if not finding.id.startswith("RES-"):
            continue
        key = res_finding_group_key(finding)
        key_to_members.setdefault(key, []).append(finding)

    emitted: set[tuple[object, ...]] = set()
    groups: list[tuple[Finding, ...]] = []
    for finding in findings:
        if not finding.id.startswith("RES-"):
            groups.append((finding,))
            continue
        key = res_finding_group_key(finding)
        if key in emitted:
            continue
        emitted.add(key)
        members = sorted(key_to_members[key], key=lambda item: item.id)
        groups.append(tuple(members))
    return groups


def _workloads_display(findings: Sequence[Finding]) -> str:
    names = sorted({f.workload for f in findings if f.workload})
    if not names:
        return "—"
    if len(names) <= 10:
        return ", ".join(f"`{name}`" for name in names)
    shown = ", ".join(f"`{name}`" for name in names[:10])
    return f"{shown} e mais {len(names) - 10}"


def _group_id_label(findings: Sequence[Finding]) -> str:
    if len(findings) == 1:
        return findings[0].id
    return f"{findings[0].id} … {findings[-1].id}"


def _group_title(findings: Sequence[Finding]) -> str:
    primary = findings[0]
    label = _group_id_label(findings)
    if len(findings) == 1:
        return f"### {label} — [{primary.category}]"
    return (
        f"### {label} — [{primary.category}] "
        f"({len(findings)} workloads)"
    )


def _format_evidence_cell(finding: Finding) -> str:
    if not finding.evidence:
        return "—"
    parts: list[str] = []
    for item in finding.evidence:
        fragment = item.description
        if item.value:
            fragment += f": `{item.value}`"
        if item.container:
            fragment += f" (container `{item.container}`)"
        parts.append(fragment)
    return "; ".join(parts).replace("|", "\\|")


def _format_grouped_evidence(findings: Sequence[Finding]) -> str:
    if len(findings) == 1:
        finding = findings[0]
        if not finding.evidence:
            return "- Nenhuma evidência estruturada registrada."
        lines: list[str] = []
        for ev in finding.evidence:
            parts = [f"- {ev.description}"]
            if ev.value:
                parts.append(f": `{ev.value}`")
            if ev.field_path:
                parts.append(f" ({ev.field_path})")
            if ev.file_path:
                parts.append(f" ← {ev.file_path}")
            lines.append("".join(parts))
        return "\n".join(lines)

    rows = [
        (
            f"`{finding.workload or '—'}`",
            f"`{finding.container}`" if finding.container else "—",
            _format_evidence_cell(finding),
        )
        for finding in findings
    ]
    header = "| Workload | Container | Evidência |\n| --- | --- | --- |"
    body = "\n".join(
        f"| {workload} | {container} | {evidence} |"
        for workload, container, evidence in rows
    )
    return f"{header}\n{body}"


def _format_grouped_sources(findings: Sequence[Finding]) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        for src in finding.sources:
            key = (src.resource_kind, src.resource_name, src.file_path)
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"- `{src.resource_kind}/{src.resource_name}` "
                f"← {src.file_path}"
            )
    return lines


def format_grouped_finding(findings: Sequence[Finding]) -> str:
    """Formata um finding isolado ou um grupo de findings RES-* equivalentes."""
    if len(findings) == 1:
        return format_finding(findings[0])

    primary = findings[0]
    lines = [
        _group_title(findings),
        "",
        f"**Severidade:** {primary.severity.value}",
        f"**Confiança:** {primary.confidence.value}",
        f"**Workloads afetados ({len(findings)}):** {_workloads_display(findings)}",
        "",
        "**Evidências:**",
        "",
        _format_grouped_evidence(findings),
        "",
        "**Análise:**",
        "",
        primary.analysis,
    ]
    if primary.impact:
        lines.extend(["", "**Impacto potencial:**", "", primary.impact])
    if primary.recommendation:
        lines.extend(["", "**Recomendação:**", "", primary.recommendation])
    if primary.limitation:
        lines.extend(["", "**Limitação:**", "", primary.limitation])

    source_lines = _format_grouped_sources(findings)
    if source_lines:
        lines.extend(["", "**Origem dos dados:**", *source_lines])

    return "\n".join(lines)


def grouped_finding_anchor_tags(findings: Sequence[Finding]) -> str:
    """Âncoras HTML para todos os IDs do grupo (links do índice e recomendações)."""
    return "\n".join(
        f'<a id="{finding.id.lower()}"></a>'
        for finding in findings
    )


def severity_sort_key(findings: Sequence[Finding]) -> tuple[int, str]:
    order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }
    primary = findings[0]
    return (order.get(primary.severity, 5), primary.id)
