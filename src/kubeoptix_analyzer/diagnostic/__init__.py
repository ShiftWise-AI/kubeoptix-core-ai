"""Diagnóstico de ingestão e normalização."""

from kubeoptix_analyzer.diagnostic.aggregator import summarize_workloads, summarize_worknodes
from kubeoptix_analyzer.diagnostic.report import format_diagnostic_report, print_diagnostic_report
from kubeoptix_analyzer.diagnostic.runner import DiagnosticRunner

__all__ = [
    "DiagnosticRunner",
    "format_diagnostic_report",
    "print_diagnostic_report",
    "summarize_workloads",
    "summarize_worknodes",
]
