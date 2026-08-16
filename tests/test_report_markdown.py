"""Testes do gerador de relatório Markdown."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.markdown import MarkdownReportGenerator, write_assessment_report
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"
OTHER_NAMESPACE = "other-ns-prd"


@pytest.fixture
def analysis_tree(tmp_path: Path) -> Path:
    base = tmp_path / "metadados"
    ns = base / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app / "deployments" / "backend-acesso-app.yaml",
    )
    pods = ns / "resources" / "pods"
    pods.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_backend_acesso_app.yaml", pods / "pod.yaml")
    metrics = ns / "resources" / "pods.metrics.k8s.io"
    metrics.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_metrics_backend_acesso_app.yaml", metrics / "m.yaml")

    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")
    return base


def test_markdown_report_structure(analysis_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    assert "# Relatório de Assessment" in md
    assert "## 1. Sumário executivo" in md
    assert "## 20. Limitações da análise" in md
    assert "backend-acesso-app" in md
    assert "**Análise:**" in md
    assert "**Confiança:**" in md
    assert "request" in md.lower()
    assert "usage" in md.lower() or "PodMetrics" in md
    assert "Principais achados" in md
    assert "Pool de scheduling relevante" in md


def test_markdown_findings_section_is_index_not_duplicate(
    analysis_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    section_15_start = md.index("## 15. Findings")
    section_16_start = md.index("## 16. Oportunidades")
    section_15 = md[section_15_start:section_16_start]

    assert "| ID | Severidade |" in section_15
    assert section_15.count("**Origem dos dados:**") == 0
    analysis_count = md.count("**Análise:**")
    assert analysis_count == bundle.analysis.finding_count


def test_markdown_distinguishes_usage_from_request(
    analysis_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    assert "uso real medido" in md or "CPU usage" in md
    assert "não representam uso real" in md or "não são requests" in md


def test_write_assessment_report_filename(analysis_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    out = tmp_path / "output"
    path = write_assessment_report(bundle, out)

    assert path == out / f"{EXAMPLE_NAMESPACE}.md"
    assert path.is_file()
    assert path.read_text(encoding="utf-8").startswith("# Relatório de Assessment")


def test_conclusion_derives_priorities_from_findings_not_hardcoded(
    tmp_path: Path,
) -> None:
    """Conclusão não deve herdar texto fixo de outro namespace (ex.: 'backends')."""
    base = tmp_path / "metadados"
    ns = base / OTHER_NAMESPACE
    app = ns / "apps" / "other-api"
    (app / "deployments").mkdir(parents=True)
    deployment = FIXTURES / "deployment_backend_acesso_app.yaml"
    content = deployment.read_text(encoding="utf-8")
    content = content.replace("example-ns-prd", OTHER_NAMESPACE)
    content = content.replace("backend-acesso-app", "other-api")
    (app / "deployments" / "other-api.yaml").write_text(content, encoding="utf-8")

    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")

    config = AnalyzerConfig(
        workloads_base=base,
        worknodes_path=nodes,
    )
    bundle = AssessmentPipeline(config).run(OTHER_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    assert f"`{OTHER_NAMESPACE}`" in md
    assert EXAMPLE_NAMESPACE not in md
    assert "backend-acesso" not in md
    conclusion_start = md.index("## 19. Conclusão")
    conclusion = md[conclusion_start:]
    assert "backends" not in conclusion.lower()
    assert OTHER_NAMESPACE in conclusion
