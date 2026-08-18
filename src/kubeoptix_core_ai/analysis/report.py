"""Formatação de findings para exibição."""

from __future__ import annotations

from kubeoptix_core_ai.models.finding import AnalysisReport, Finding


def format_finding(finding: Finding) -> str:
    lines = [
        f"### {finding.id}",
        "",
        f"**Categoria:** {finding.category}",
        f"**Severidade:** {finding.severity.value}",
        f"**Confiança:** {finding.confidence.value}",
    ]
    if finding.workload:
        lines.append(f"**Workload:** {finding.workload}")
    if finding.container:
        lines.append(f"**Container:** {finding.container}")
    lines.append("")
    lines.append("**Evidências:**")
    if finding.evidence:
        for ev in finding.evidence:
            parts = [f"- {ev.description}"]
            if ev.value:
                parts.append(f": `{ev.value}`")
            if ev.field_path:
                parts.append(f" ({ev.field_path})")
            if ev.file_path:
                parts.append(f" ← {ev.file_path}")
            lines.append("".join(parts))
    else:
        lines.append("- Nenhuma evidência estruturada registrada.")
    lines.extend(["", "**Análise:**", "", finding.analysis])
    if finding.impact:
        lines.extend(["", "**Impacto potencial:**", "", finding.impact])
    if finding.recommendation:
        lines.extend(["", "**Recomendação:**", "", finding.recommendation])
    if finding.limitation:
        lines.extend(["", "**Limitação:**", "", finding.limitation])
    if finding.sources:
        lines.extend(["", "**Origem dos dados:**"])
        for src in finding.sources:
            lines.append(
                f"- `{src.resource_kind}/{src.resource_name}` "
                f"← {src.file_path}"
            )
    return "\n".join(lines)


def print_analysis_report(report: AnalysisReport) -> None:
    title = "Análise de workloads"
    if report.ml_enabled:
        title += " (determinística + ML local)"
    else:
        title += " (determinística)"
    print(f"# {title} — namespace `{report.namespace}`")
    print()
    print(f"- Workloads analisados: {report.workloads_analyzed}")
    print(f"- Worknodes considerados: {report.worknodes_considered}")
    print(f"- Findings: {report.finding_count}")
    print()

    if report.limitations:
        print("## Limitações")
        for lim in report.limitations:
            print(f"- {lim}")
        print()

    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for f in report.findings:
        by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1
        by_category[f.category] = by_category.get(f.category, 0) + 1

    print("## Resumo por severidade")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
        if sev in by_severity:
            print(f"- {sev}: {by_severity[sev]}")
    print()
    print("## Resumo por categoria")
    for cat, count in sorted(by_category.items()):
        print(f"- {cat}: {count}")
    print()
    print("## Findings")
    print()
    for finding in report.findings:
        print(format_finding(finding))
        print()
