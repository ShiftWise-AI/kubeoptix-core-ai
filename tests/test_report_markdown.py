"""Testes do gerador de relatório Markdown."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.finding_groups import finding_section_ids
from kubeoptix_core_ai.report.markdown import (
    REPORT_FILE_ENCODING,
    REPORT_FILE_LANGUAGE,
    MarkdownReportGenerator,
    write_assessment_report,
)
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

    assert md.startswith("---\n")
    assert f"lang: {REPORT_FILE_LANGUAGE}\n" in md
    assert "babel-lang: brazil\n" in md
    assert "# Relatório de Assessment" in md
    assert "## 1. Sumário executivo" in md
    assert "## 2. Inventário do namespace / aplicações" in md
    assert "## 3. Arquitetura reversa" in md
    assert "## 4. Recursos de CPU e memória" in md
    assert "## 5. Observabilidade (métricas, logs, monitoramento)" in md
    assert "## 8. Referências utilizadas" in md
    assert "backend-acesso-app" in md
    assert "**Namespace analisado:**" in md
    assert "**Fonte dos dados:**" in md
    assert "request" in md.lower()
    assert "PodMetrics" in md or "uso real" in md.lower()
    assert "Principais achados" in md
    assert "Pool de scheduling relevante" in md


def test_markdown_distinguishes_usage_from_request(
    analysis_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    assert "request" in md.lower() and ("limit" in md.lower() or "PodMetrics" in md)
    assert "uso real" in md.lower() or "PodMetrics" in md


def test_write_assessment_report_filename(analysis_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    out = tmp_path / "output"
    path = write_assessment_report(bundle, out)

    assert path == out / f"ml-{EXAMPLE_NAMESPACE}.md"
    assert path.is_file()
    raw = path.read_bytes()
    content = raw.decode("utf-8")
    assert content.startswith("---\n")
    assert f"lang: {REPORT_FILE_LANGUAGE}\n" in content
    assert "# Relatório de Assessment" in content
    assert "Relatório" in content
    assert "Análise" in content or "análise" in content.lower()


def test_write_assessment_report_utf8_encoding(analysis_tree: Path, tmp_path: Path) -> None:
    assert REPORT_FILE_ENCODING == "utf-8"
    assert REPORT_FILE_LANGUAGE == "pt-BR"

    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    path = write_assessment_report(bundle, tmp_path / "out")

    raw = path.read_bytes()
    assert raw.decode("utf-8")  # levanta UnicodeDecodeError se não for UTF-8
    assert not raw.startswith(b"\xff\xfe")
    assert not raw.startswith(b"\xfe\xff")


def test_references_section(analysis_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    refs_start = md.index("## 8. Referências utilizadas")
    refs = md[refs_start:]

    assert "### Documentação técnica — Red Hat" in refs
    assert "### Documentação técnica complementar (upstream)" in refs
    assert "### Referências bibliográficas — Red Hat" in refs
    assert "### Referências bibliográficas complementares" in refs
    assert "### Ferramentas e métodos analíticos" in refs
    assert "KubeDiagrams" in refs
    assert "Scikit-learn" in refs
    assert "Isolation Forest" in refs
    assert (
        "| CPU e memória (requests/limits) | "
        "[Red Hat OpenShift — Recursos de computação para scheduling]"
        "(https://docs.openshift.com/container-platform/latest/nodes/scheduling/nodes-scheduler-compute-resources.html) |"
    ) in refs
    assert "docs.openshift.com" in refs
    assert "OpenShift for Developers" in refs
    assert "Kubernetes Patterns" in refs
    assert "Site Reliability Engineering" in refs
    assert refs.startswith("## 8. Referências utilizadas")


def test_action_plan_section(analysis_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    assert "## 7. Plano de ação" in md
    assert "### Plano de ação" in md
    assert "Lista consolidada" in md or "Prioridade" in md
    assert "### Lista consolidada" in md or "### Plano de ação" in md

    section_ids = finding_section_ids(bundle.analysis.findings)
    assert section_ids
