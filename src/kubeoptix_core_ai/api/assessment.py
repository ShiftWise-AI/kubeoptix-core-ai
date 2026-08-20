"""Serviço de análise de namespaces para a API REST."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from kubeoptix_core_ai.api.progress import RunProgress
from kubeoptix_core_ai.config import (
    ENV_METADATA_DIR,
    ENV_OUTPUT_DIR,
    AnalyzerConfig,
)
from kubeoptix_core_ai.discovery.inventory import (
    NamespaceFileInventory,
    scan_namespace_files,
)
from kubeoptix_core_ai.discovery.scanner import list_namespace_dirs
from kubeoptix_core_ai.errors import AnalyzerError, ConfigurationError
from kubeoptix_core_ai.report.markdown import (
    REPORT_FILE_ENCODING,
    MarkdownReportGenerator,
)
from kubeoptix_core_ai.visualization.markdown import embed_markdown_images
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline
from kubeoptix_core_ai.visualization.pipeline import report_assets_prefix

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


def build_report_filename(namespace: str) -> str:
    """Monta nome de arquivo `<namespace>.md`."""
    return f"{namespace}.md"


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
        progress: RunProgress | None = None,
    ) -> AnalysisRunResult:
        ordered = dedupe_namespaces(namespaces)
        self.validate_namespaces(ordered)

        config = AnalyzerConfig.from_metadata_dir(self._assessment_dir)
        pipeline = AssessmentPipeline(config)
        self._reports_dir.mkdir(parents=True, exist_ok=True)

        inventories: dict[str, NamespaceFileInventory] = {}
        if progress is not None:
            progress.set_running()
            total_files = 0
            for namespace in ordered:
                inventory = scan_namespace_files(config.namespace_path(namespace))
                inventories[namespace] = inventory
                total_files += inventory.files_to_process_count
            progress.set_total(total_files)

        reports: list[NamespaceReportResult] = []

        for index, namespace in enumerate(ordered):
            if progress is not None:
                progress.begin_namespace(index, namespace)
            try:
                bundle = pipeline.run(
                    namespace,
                    enable_ml=enable_ml,
                    inventory=inventories.get(namespace),
                    progress=progress,
                )
            except AnalyzerError:
                raise
            except Exception as exc:
                raise AnalyzerError(
                    f"Falha ao analisar o namespace {namespace!r}: {exc}"
                ) from exc

            filename = build_report_filename(namespace)
            report_path = self._reports_dir / filename
            assets_dir = self._reports_dir / report_assets_prefix(namespace)
            if progress is not None:
                progress.markdown_started()
            content = MarkdownReportGenerator().generate(bundle, assets_dir=assets_dir)
            content = embed_markdown_images(content, markdown_dir=self._reports_dir)
            report_path.write_bytes(content.encode(REPORT_FILE_ENCODING))
            if progress is not None:
                progress.namespace_report_written(str(report_path))

            reports.append(
                NamespaceReportResult(
                    namespace=namespace,
                    report_path=report_path,
                    workloads_analyzed=bundle.analysis.workloads_analyzed,
                    finding_count=bundle.analysis.finding_count,
                )
            )

        result = AnalysisRunResult(status="SUCCESS", reports=tuple(reports))
        if progress is not None:
            last_report = str(reports[-1].report_path) if reports else None
            progress.completed(last_report)
        return result
