"""Testes do gerador de relatório Markdown."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.finding_groups import finding_section_ids, group_identical_res_findings
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
    assert "## 1. Legenda de siglas" in md
    assert "## 2. Sumário executivo" in md
    assert "## 14. Events" in md
    assert "## 15. Atualização de Operators (OLM)" in md
    assert "## 23. Limitações da análise" in md
    assert "## 24. Referências" in md
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

    section_18_start = md.index("## 18. Findings")
    section_19_start = md.index("## 19. Oportunidades")
    section_16 = md[section_18_start:section_19_start]

    assert "| ID | Severidade |" in section_16
    assert section_16.count("**Origem dos dados:**") == 0
    analysis_count = md.count("**Análise:**") + md.count("| ID | Workload | Evidência |")
    grouped_count = len(group_identical_res_findings(bundle.analysis.findings))
    assert analysis_count == grouped_count


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


def test_acronyms_legend_section(analysis_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    legend_start = md.index("## 1. Legenda de siglas")
    legend_end = md.index("## 2. Sumário executivo")
    legend = md[legend_start:legend_end]

    assert "### Categorias de findings" in legend
    assert "### Níveis de severidade" in legend
    assert "### Níveis de confiança" in legend
    assert "### Termos técnicos" in legend
    assert "| CPU | Dimensionamento e uso de CPU |" in legend
    assert "| CRITICAL | Risco imediato" in legend
    assert "| HPA | Horizontal Pod Autoscaler |" in legend
    assert "| EVENT | Events Kubernetes/OpenShift (Warning) |" in legend
    assert "| MLFLEET | Comparação com percentis da frota corporativa |" in legend
    assert "| RES-* | Prefixo dos IDs" in legend


def test_references_section(analysis_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    refs_start = md.index("## 24. Referências")
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
    assert refs.startswith("## 24. Referências")
    limitations_end = md.index("## 23. Limitações da análise")
    assert refs_start > limitations_end


def test_recommendations_link_to_finding_anchors(
    analysis_tree: Path, tmp_path: Path
) -> None:
    """Recomendações e índice devem linkar para âncoras dos findings nas seções."""
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    linked_findings = {
        f.id for f in bundle.analysis.findings if f.recommendation
    }
    assert linked_findings

    section_ids = finding_section_ids(bundle.analysis.findings)
    for finding_id in linked_findings:
        section_id = section_ids[finding_id]
        anchor = section_id.lower()
        assert f"### {section_id}" in md
        assert f"[`{finding_id}`](#{anchor})" in md

    rec_start = md.index("## 21. Recomendações")
    rec_end = md.index("## 22. Conclusão")
    recommendations = md[rec_start:rec_end]
    assert "[`RES-" in recommendations
    assert "(#res-" in recommendations


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
    conclusion_start = md.index("## 22. Conclusão")
    conclusion = md[conclusion_start:]
    assert "backends" not in conclusion.lower()
    assert OTHER_NAMESPACE in conclusion
