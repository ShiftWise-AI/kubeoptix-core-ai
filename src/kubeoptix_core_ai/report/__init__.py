"""Geração de relatórios de assessment em Markdown."""

from kubeoptix_core_ai.report.markdown import (
    REPORT_FILE_ENCODING,
    REPORT_FILE_LANGUAGE,
    MarkdownReportGenerator,
    write_assessment_report,
)
from kubeoptix_core_ai.report.pipeline import AssessmentBundle, AssessmentPipeline

__all__ = [
    "AssessmentBundle",
    "AssessmentPipeline",
    "MarkdownReportGenerator",
    "REPORT_FILE_ENCODING",
    "REPORT_FILE_LANGUAGE",
    "write_assessment_report",
]
