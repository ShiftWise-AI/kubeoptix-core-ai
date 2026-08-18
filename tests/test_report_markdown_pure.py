"""Validação de que relatórios gerados são Markdown puro (sem HTML embutido)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.markdown import MarkdownReportGenerator, write_assessment_report
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline

TRAINING_INVENTORY = Path(
    "/home/parraes/redhat/shiftwise-ai/base-treinamento/metadados"
)
TRAINING_NAMESPACE = "offering-container-cj"

_FORBIDDEN_HTML_FRAGMENTS = (
    "<div",
    "</div>",
    "<style",
    "</style>",
    "<script",
    "</script>",
    "<svg",
    "</svg>",
)

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_FENCED_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]+`")


def _prose_without_code(content: str) -> str:
    """Remove blocos e trechos em código antes de procurar tags HTML na prosa."""
    without_fences = _FENCED_CODE_BLOCK.sub("", content)
    return _INLINE_CODE.sub("", without_fences)


def assert_pure_markdown(content: str) -> None:
    """Falha se o conteúdo contiver tags HTML de apresentação."""
    for fragment in _FORBIDDEN_HTML_FRAGMENTS:
        assert fragment not in content, (
            f"Relatório contém HTML proibido ({fragment!r}). "
            "Gráficos devem usar Mermaid ou tabelas Markdown."
        )

    prose = _prose_without_code(content)
    html_tags = _HTML_TAG_PATTERN.findall(prose)
    assert not html_tags, (
        f"Relatório contém tags HTML inesperadas na prosa: {html_tags[:5]}"
    )


@pytest.fixture
def training_inventory_available() -> Path:
    if not TRAINING_INVENTORY.is_dir():
        pytest.skip(f"Inventário de treinamento ausente: {TRAINING_INVENTORY}")
    ns_dir = TRAINING_INVENTORY / TRAINING_NAMESPACE
    if not ns_dir.is_dir():
        pytest.skip(f"Namespace {TRAINING_NAMESPACE!r} ausente no inventário")
    return TRAINING_INVENTORY


def test_generated_report_is_pure_markdown(
    training_inventory_available: Path, tmp_path: Path
) -> None:
    """Gera relatório completo e valida ausência de HTML no arquivo .md."""
    config = AnalyzerConfig.from_metadata_dir(training_inventory_available)
    bundle = AssessmentPipeline(config).run(TRAINING_NAMESPACE)
    path = write_assessment_report(bundle, tmp_path / "reports")

    assert path.suffix == ".md"
    content = path.read_text(encoding="utf-8")

    assert_pure_markdown(content)
    assert "```mermaid" in content
    assert "xychart-beta" in content or "flowchart" in content or "pie title" in content


def test_markdown_generator_output_has_no_html(
    training_inventory_available: Path,
) -> None:
    """Valida o conteúdo retornado pelo gerador (não apenas o arquivo em disco)."""
    config = AnalyzerConfig.from_metadata_dir(training_inventory_available)
    bundle = AssessmentPipeline(config).run(TRAINING_NAMESPACE)
    content = MarkdownReportGenerator().generate(bundle)

    assert_pure_markdown(content)
