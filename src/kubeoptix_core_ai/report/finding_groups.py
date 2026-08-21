"""Agrupamento de findings RES-* e ML-* equivalentes para leitura humana."""

from __future__ import annotations

import re
from collections.abc import Sequence

from kubeoptix_core_ai.analysis.report import format_finding
from kubeoptix_core_ai.models.finding import Finding, Severity

_NUMERIC_RE = re.compile(r"\d+(?:\.\d+)?")
_QUOTED_RE = re.compile(r"`[^`]+`")
_GROUPABLE_ID_PREFIXES = ("RES-", "ML-")


def _is_groupable(finding: Finding) -> bool:
    return finding.id.startswith(_GROUPABLE_ID_PREFIXES)


def _normalize_analysis(text: str) -> str:
    """Remove valores e nomes específicos para comparar o padrão do achado."""
    normalized = _QUOTED_RE.sub("`<valor>`", text)
    normalized = _NUMERIC_RE.sub("<n>", normalized)
    return normalized


def res_finding_group_key(finding: Finding) -> tuple[object, ...]:
    """Chave de equivalência para findings agrupáveis (ignora workload e valores)."""
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
    """Agrupa findings RES-* e ML-* equivalentes, preservando a ordem da primeira ocorrência."""
    key_to_members: dict[tuple[object, ...], list[Finding]] = {}
    for finding in findings:
        if not _is_groupable(finding):
            continue
        key = res_finding_group_key(finding)
        key_to_members.setdefault(key, []).append(finding)

    emitted: set[tuple[object, ...]] = set()
    groups: list[tuple[Finding, ...]] = []
    for finding in findings:
        if not _is_groupable(finding):
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


def _group_unit(findings: Sequence[Finding]) -> str:
    if findings and findings[0].id.startswith("ML-"):
        return "itens"
    return "workloads"


def _group_title(findings: Sequence[Finding]) -> str:
    primary = findings[0]
    if len(findings) == 1:
        return f"### {primary.id} — [{primary.category}]"
    label = _group_id_label(findings)
    return (
        f"### {primary.id} — [{primary.category}] "
        f"({len(findings)} {_group_unit(findings)}; {label})"
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


def _format_grouped_ml_table(findings: Sequence[Finding]) -> str:
    """Tabela compacta para findings ML-* equivalentes (um bloco em vez de N seções)."""
    rows = [
        (
            finding.id,
            f"`{finding.workload}`" if finding.workload else "—",
            _format_evidence_cell(finding),
        )
        for finding in findings
    ]
    header = "| ID | Workload | Evidência |\n| --- | --- | --- |"
    body = "\n".join(f"| `{fid}` | {workload} | {evidence} |" for fid, workload, evidence in rows)
    return f"{header}\n{body}"


def format_grouped_finding(findings: Sequence[Finding]) -> str:
    """Formata um finding isolado ou um grupo de findings RES-*/ML-* equivalentes."""
    if len(findings) == 1:
        return format_finding(findings[0])

    primary = findings[0]
    if primary.id.startswith("ML-"):
        lines = [
            _group_title(findings),
            "",
            f"**Severidade:** {primary.severity.value}",
            f"**Confiança:** {primary.confidence.value}",
            f"**Itens agrupados ({len(findings)}):** {_workloads_display(findings)}",
            "",
            "Findings equivalentes do mesmo padrão ML; detalhes por item na tabela.",
            "",
            _format_grouped_ml_table(findings),
        ]
        if primary.impact:
            lines.extend(["", "**Impacto potencial:**", "", primary.impact])
        if primary.recommendation:
            lines.extend(["", "**Recomendação:**", "", primary.recommendation])
        if primary.limitation:
            lines.extend(["", "**Limitação:**", "", primary.limitation])
        return "\n".join(lines)

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


def finding_section_ids(findings: Sequence[Finding]) -> dict[str, str]:
    """Mapeia cada finding ao ID de seção Markdown (cabeçalho `###`) no relatório."""
    section_ids: dict[str, str] = {}
    for group in group_identical_res_findings(findings):
        section_id = group[0].id
        for finding in group:
            section_ids[finding.id] = section_id
    return section_ids


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
