"""Testes do gerador de relatório Markdown."""

from __future__ import annotations

import shutil
from dataclasses import replace
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
    assert "### Sugestões de configuração Kubernetes/OpenShift" in md
    assert "| Campo | Valor no assessment |" in md
    assert (
        "Os valores sugeridos reproduzem apenas requests e limits declarados nos "
        "manifests do assessment." in md
    )


def test_resource_configuration_suggestions_use_declared_values_only(
    analysis_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    start = md.index("### Sugestões de configuração Kubernetes/OpenShift")
    end = md.index("### Visualizações", start)
    suggestions = md[start:end]

    assert "| `resources.requests.cpu` | `350m` |" in suggestions
    assert "| `resources.requests.memory` | `384Mi` |" in suggestions
    assert "| `resources.limits.cpu` | `700m` |" in suggestions
    assert "| `resources.limits.memory` | `2Gi` |" in suggestions
    assert "    cpu: 350m" in suggestions
    assert "    memory: 384Mi" in suggestions
    assert "    cpu: 700m" in suggestions
    assert "    memory: 2Gi" in suggestions
    assert "6365928n" not in suggestions
    assert "841428Ki" not in suggestions


def test_resource_suggestions_mark_missing_values_without_inventing_them(
    analysis_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    workload = bundle.context.workloads[0]
    container = workload.containers[0].model_copy(update={"cpu_request": None})
    workload = workload.model_copy(update={"containers": (container,)})
    workload_bundle = bundle.context.bundle.model_copy(update={"workloads": (workload,)})
    context = replace(bundle.context, bundle=workload_bundle)
    bundle = replace(bundle, context=context)

    md = MarkdownReportGenerator().generate(bundle)
    start = md.index("### Sugestões de configuração Kubernetes/OpenShift")
    end = md.index("### Visualizações", start)
    suggestions = md[start:end]

    assert "| `resources.requests.cpu` | `Não declarado no assessment` |" in suggestions
    assert "requests:\n    memory: 384Mi" in suggestions
    assert "    cpu: 350m" not in suggestions


@pytest.mark.parametrize(
    (
        "locale",
        "title",
        "summary",
        "action_plan",
        "resource_heading",
        "resource_description",
        "resource_labels",
        "workload_label",
        "container_label",
    ),
    [
        (
            "en-US",
            "Assessment Report",
            "Executive summary",
            "Action plan",
            "Kubernetes/OpenShift configuration suggestions",
            "Suggested values reproduce only requests and limits declared in the assessment manifests. Usage metrics are point-in-time snapshots and cannot be used to calculate new sizing values; undeclared fields are marked unavailable and omitted from the YAML.",
            "| Field | Assessment value |",
            "Workload:",
            "Container:",
        ),
        (
            "es-ES",
            "Informe de evaluación",
            "Resumen ejecutivo",
            "Plan de acción",
            "Sugerencias de configuración de Kubernetes/OpenShift",
            "Los valores sugeridos reproducen únicamente los requests y limits declarados en los manifiestos de la evaluación. Las métricas de uso son instantáneas puntuales y no permiten calcular nuevos valores de dimensionamiento; los campos no declarados se indican como no disponibles y se omiten del YAML.",
            "| Campo | Valor en la evaluación |",
            "Workload:",
            "Contenedor:",
        ),
        (
            "it-IT",
            "Rapporto di valutazione",
            "Riepilogo esecutivo",
            "Piano d'azione",
            "Suggerimenti di configurazione Kubernetes/OpenShift",
            "I valori suggeriti riproducono esclusivamente request e limit dichiarati nei manifest dell'assessment. Le metriche di utilizzo sono snapshot puntuali e non consentono di calcolare nuovi valori di dimensionamento; i campi non dichiarati sono indicati come non disponibili e omessi dal YAML.",
            "| Campo | Valore nell'assessment |",
            "Workload:",
            "Container:",
        ),
    ],
)
def test_markdown_report_is_fully_localized(
    analysis_tree: Path,
    tmp_path: Path,
    locale: str,
    title: str,
    summary: str,
    action_plan: str,
    resource_heading: str,
    resource_description: str,
    resource_labels: str,
    workload_label: str,
    container_label: str,
) -> None:
    config = AnalyzerConfig(
        workloads_base=analysis_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator(locale).generate(bundle)

    assert f"lang: {locale}" in md
    assert f"# {title}" in md
    assert f"## 1. {summary}" in md
    assert f"## 7. {action_plan}" in md
    assert f"### {resource_heading}" in md
    assert resource_description in md
    assert resource_labels in md
    assert f"#### {workload_label}" in md
    assert container_label in md
    assert "Os valores sugeridos reproduzem apenas" not in md
    assert "snapshots puntuais" not in md
    for portuguese_text in (
        "Este relatório foi produzido",
        "foi analisado com",
        "Tipos de artefato considerados",
        "Nenhum conteúdo de Secret",
        "Diagrama gerado a partir",
        "Uso real é",
        "**Evidências:**",
        "**Análise:**",
        "**Impacto potencial:**",
        "**Recomendação:**",
        "| Prioridade | Ação |",
        "Fontes consultadas para fundamentar",
    ):
        assert portuguese_text not in md


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
