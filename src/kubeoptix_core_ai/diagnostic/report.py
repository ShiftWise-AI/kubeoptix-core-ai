"""Formatação do relatório de diagnóstico para exibição."""

from __future__ import annotations

from kubeoptix_core_ai.models.diagnostic import (
    IngestionDiagnosticReport,
    ResourceTotals,
)


def _print_resource_section(title: str, totals: ResourceTotals) -> None:
    print(f"\n### {title}")
    if not totals.available:
        print(f"- Total agregado: indisponível")
        if totals.note:
            print(f"- Observação: {totals.note}")
    else:
        print(f"- Total agregado (derivado): {totals.display}")
        if totals.note:
            print(f"- Observação: {totals.note}")
    print(f"- Entradas por container/nó: {len(totals.entries)}")
    for entry in totals.entries:
        print(
            f"  - {entry.workload}/{entry.container}: `{entry.value_raw}` "
            f"({entry.field_path} ← {entry.file_path})"
        )


def format_diagnostic_report(report: IngestionDiagnosticReport) -> str:
    """Retorna relatório de diagnóstico em texto."""
    lines: list[str] = [
        f"# Diagnóstico de ingestão — namespace `{report.namespace}`",
        "",
        "## Arquivos",
        f"- Encontrados: {report.files_found_count}",
        f"- Elegíveis para processamento: {report.files_to_process_count}",
        f"- Processados com sucesso: {report.files_processed_count}",
        f"- Ignorados: {report.files_ignored_count}",
        "",
        "## Erros de parsing",
    ]

    if report.parse_errors:
        for err in report.parse_errors:
            lines.append(f"- {err}")
    else:
        lines.append("- Nenhum")

    lines.extend(
        [
            "",
            "## Workloads",
            f"- Quantidade: {report.workloads.workload_count}",
            f"- Containers: {report.workloads.container_count}",
        ]
    )

    if report.workloads.replicas_desired_total is not None:
        lines.append(
            f"- Réplicas (soma spec.replicas): {report.workloads.replicas_desired_total}"
        )
    else:
        lines.append("- Réplicas (soma spec.replicas): indisponível")

    for label, totals in (
        ("CPU requests", report.workloads.cpu_requests),
        ("CPU limits", report.workloads.cpu_limits),
        ("Memória requests", report.workloads.memory_requests),
        ("Memória limits", report.workloads.memory_limits),
    ):
        lines.append(f"\n### {label}")
        if totals.available:
            lines.append(f"- Total agregado (derivado): {totals.display}")
        else:
            lines.append("- Total agregado: indisponível")
        if totals.note:
            lines.append(f"- Observação: {totals.note}")
        lines.append(f"- Entradas: {len(totals.entries)}")

    lines.extend(
        [
            "",
            "## Worknodes",
            f"- Quantidade: {report.worknodes.worknode_count}",
        ]
    )

    for label, totals in (
        ("CPU capacity", report.worknodes.cpu_capacity),
        ("CPU allocatable", report.worknodes.cpu_allocatable),
        ("Memória capacity", report.worknodes.memory_capacity),
        ("Memória allocatable", report.worknodes.memory_allocatable),
    ):
        lines.append(f"\n### {label}")
        if totals.available:
            lines.append(f"- Total agregado (derivado): {totals.display}")
        else:
            lines.append("- Total agregado: indisponível")
        if totals.note:
            lines.append(f"- Observação: {totals.note}")

    if report.worknodes.parse_errors:
        lines.append("\n### Erros de parsing (worknodes)")
        for err in report.worknodes.parse_errors:
            lines.append(f"- {err}")

    return "\n".join(lines)


def print_diagnostic_report(report: IngestionDiagnosticReport) -> None:
    """Imprime relatório de diagnóstico formatado no stdout."""
    print(format_diagnostic_report(report))

    if report.files_ignored:
        print("\n## Arquivos ignorados (amostra até 20)")
        for path, reason in report.files_ignored[:20]:
            print(f"- {path}")
            print(f"  Motivo: {reason}")
        if len(report.files_ignored) > 20:
            print(f"- ... e mais {len(report.files_ignored) - 20} arquivos ignorados")

    print("\n## Detalhamento de recursos por workload")
    _print_resource_section("CPU requests", report.workloads.cpu_requests)
    _print_resource_section("CPU limits", report.workloads.cpu_limits)
    _print_resource_section("Memória requests", report.workloads.memory_requests)
    _print_resource_section("Memória limits", report.workloads.memory_limits)

    print("\n## Detalhamento de capacidade por worknode")
    _print_resource_section("CPU capacity", report.worknodes.cpu_capacity)
    _print_resource_section("CPU allocatable", report.worknodes.cpu_allocatable)
    _print_resource_section("Memória capacity", report.worknodes.memory_capacity)
    _print_resource_section("Memória allocatable", report.worknodes.memory_allocatable)
