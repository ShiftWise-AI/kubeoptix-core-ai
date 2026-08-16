"""Geração de relatórios de assessment em Markdown."""

from kubeoptix_core_ai.report.markdown import MarkdownReportGenerator, write_assessment_report
from kubeoptix_core_ai.report.pipeline import AssessmentBundle, AssessmentPipeline

__all__ = [
    "AssessmentBundle",
    "AssessmentPipeline",
    "MarkdownReportGenerator",
    "write_assessment_report",
]
