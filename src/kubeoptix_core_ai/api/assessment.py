"""Serviço de análise de namespaces para a API REST."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kubeoptix_core_ai.config import (
    ENV_METADATA_DIR,
    ENV_OUTPUT_DIR,
    AnalyzerConfig,
)
from kubeoptix_core_ai.discovery.scanner import list_namespace_dirs
from kubeoptix_core_ai.errors import AnalyzerError, ConfigurationError
from kubeoptix_core_ai.report.markdown import (
    REPORT_FILE_ENCODING,
    MarkdownReportGenerator,
)
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline

DEFAULT_ASSESSMENT_DIR = Path("/app/data/assessment")
DEFAULT_REPORTS_DIR = Path("/app/data/reports")


class NamespaceNotFoundError(Exception):
    """Um ou mais namespaces não existem nos dados de assessment."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__(
            f"Namespaces não encontrados em assessment: {', '.join(self.missing)}"
        )


@dataclass(frozen=True)
class NamespaceReportResult:
    namespace: str
    report_path: Path
    workloads_analyzed: int
    finding_count: int


@dataclass(frozen=True)
class AnalysisRunResult:
    status: str
    reports: tuple[NamespaceReportResult, ...]


def resolve_assessment_dir() -> Path:
    return Path(os.getenv(ENV_METADATA_DIR, str(DEFAULT_ASSESSMENT_DIR)))


def resolve_reports_dir() -> Path:
    return Path(os.getenv(ENV_OUTPUT_DIR, str(DEFAULT_REPORTS_DIR)))


def list_available_namespaces(assessment_dir: Path) -> frozenset[str]:
    return frozenset(p.name for p in list_namespace_dirs(assessment_dir))


def dedupe_namespaces(namespaces: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for namespace in namespaces:
        if namespace not in seen:
            seen.add(namespace)
            ordered.append(namespace)
    return ordered


def build_report_filename(
    namespace: str,
    namespaces: list[str],
    generated_at: datetime,
) -> str:
    """Monta nome de arquivo que identifica o namespace e o lote analisado."""
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    if len(namespaces) == 1:
        return f"{namespace}__{timestamp}.md"

    batch_token = "_".join(sorted(namespaces))
    if len(batch_token) > 96:
        digest = hashlib.sha256(batch_token.encode("utf-8")).hexdigest()[:12]
        batch_token = f"{batch_token[:48]}__{digest}"
    return f"{namespace}__batch-{batch_token}__{timestamp}.md"


class AssessmentService:
    """Executa análise e gera relatórios Markdown para namespaces informados."""

    def __init__(
        self,
        assessment_dir: Path | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        self._assessment_dir = (assessment_dir or resolve_assessment_dir()).resolve()
        self._reports_dir = (reports_dir or resolve_reports_dir()).resolve()

    @property
    def assessment_dir(self) -> Path:
        return self._assessment_dir

    @property
    def reports_dir(self) -> Path:
        return self._reports_dir

    def validate_namespaces(self, namespaces: list[str]) -> None:
        if not self._assessment_dir.is_dir():
            raise ConfigurationError(
                f"Diretório de assessment não encontrado: {self._assessment_dir}"
            )

        config = AnalyzerConfig.from_metadata_dir(self._assessment_dir)
        for namespace in namespaces:
            config.namespace_path(namespace)

        available = list_available_namespaces(self._assessment_dir)
        missing = [namespace for namespace in namespaces if namespace not in available]
        if missing:
            raise NamespaceNotFoundError(missing)

    def run(
        self,
        namespaces: list[str],
        *,
        enable_ml: bool | None = None,
    ) -> AnalysisRunResult:
        ordered = dedupe_namespaces(namespaces)
        self.validate_namespaces(ordered)

        config = AnalyzerConfig.from_metadata_dir(self._assessment_dir)
        pipeline = AssessmentPipeline(config)
        self._reports_dir.mkdir(parents=True, exist_ok=True)

        generated_at = datetime.now(tz=UTC)
        reports: list[NamespaceReportResult] = []

        for namespace in ordered:
            try:
                bundle = pipeline.run(namespace, enable_ml=enable_ml)
            except AnalyzerError:
                raise
            except Exception as exc:
                raise AnalyzerError(
                    f"Falha ao analisar o namespace {namespace!r}: {exc}"
                ) from exc

            filename = build_report_filename(namespace, ordered, generated_at)
            report_path = self._reports_dir / filename
            content = MarkdownReportGenerator().generate(bundle)
            report_path.write_bytes(content.encode(REPORT_FILE_ENCODING))

            reports.append(
                NamespaceReportResult(
                    namespace=namespace,
                    report_path=report_path,
                    workloads_analyzed=bundle.analysis.workloads_analyzed,
                    finding_count=bundle.analysis.finding_count,
                )
            )

        return AnalysisRunResult(status="SUCCESS", reports=tuple(reports))
