"""Testes de agrupamento de findings RES-* no relatório."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.report.finding_groups import (
    format_grouped_finding,
    group_identical_res_findings,
)
from kubeoptix_core_ai.report.markdown import MarkdownReportGenerator
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def plfat_like_tree(tmp_path: Path) -> tuple[Path, Path]:
    """Dois workloads idênticos para gerar findings RES-* duplicados."""
    base = tmp_path / "metadados"
    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")

    for workload_name in ("app-a", "app-b"):
        ns = base / EXAMPLE_NAMESPACE
        app = ns / "apps" / workload_name
        (app / "deployments").mkdir(parents=True)
        deployment = FIXTURES / "deployment_backend_acesso_app.yaml"
        content = deployment.read_text(encoding="utf-8")
        content = content.replace("backend-acesso-app", workload_name)
        (app / "deployments" / f"{workload_name}.yaml").write_text(
            content, encoding="utf-8"
        )

    return base, nodes


def test_group_identical_res_findings_merges_same_pattern(
    plfat_like_tree: tuple[Path, Path],
) -> None:
    base, nodes = plfat_like_tree
    config = AnalyzerConfig(workloads_base=base, worknodes_path=nodes)
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    res_findings = [f for f in bundle.analysis.findings if f.id.startswith("RES-")]

    groups = group_identical_res_findings(bundle.analysis.findings)
    grouped_res = [g for g in groups if len(g) > 1 and g[0].id.startswith("RES-")]

    assert res_findings
    assert grouped_res, "esperado ao menos um grupo RES-* com múltiplos workloads"

    for group in grouped_res:
        categories = {item.category for item in group}
        severities = {item.severity for item in group}
        assert len(categories) == 1
        assert len(severities) == 1


def test_markdown_groups_res_findings_in_sections(
    plfat_like_tree: tuple[Path, Path],
) -> None:
    base, nodes = plfat_like_tree
    config = AnalyzerConfig(workloads_base=base, worknodes_path=nodes)
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    md = MarkdownReportGenerator().generate(bundle)

    assert "(2 workloads" in md
    assert "**Workloads afetados (2):**" in md
    analysis_blocks = md.count("**Análise:**") + md.count("| ID | Workload | Evidência |")
    grouped = len(group_identical_res_findings(bundle.analysis.findings))
    assert analysis_blocks == grouped
    assert analysis_blocks < bundle.analysis.finding_count


def test_grouped_format_lists_per_workload_evidence() -> None:
    from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Finding, Severity

    template = dict(
        category="PROBE",
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        namespace="ns",
        analysis="O container `<valor>` não define livenessProbe.",
        impact="Impacto.",
        recommendation="Adicionar livenessProbe.",
    )
    findings = tuple(
        Finding(
            id=f"RES-PROBE-{idx:03d}",
            workload=name,
            container=name,
            evidence=(
                EvidenceItem(
                    description="livenessProbe ausente",
                    container=name,
                ),
            ),
            **template,
        )
        for idx, name in enumerate(("alpha", "beta"), start=1)
    )

    rendered = format_grouped_finding(findings)
    assert "RES-PROBE-001 … RES-PROBE-002" in rendered
    assert "| `alpha` |" in rendered
    assert "| `beta` |" in rendered


def test_group_identical_ml_findings_renders_compact_table() -> None:
    from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Finding, Severity

    template = dict(
        category="MLSIM",
        severity=Severity.INFO,
        confidence=Confidence.MEDIUM,
        namespace="ns",
        impact="Candidatos para comparação.",
        recommendation="Investigar diferenças de tráfego.",
    )
    findings = tuple(
        Finding(
            id=f"ML-MLSIM-{idx:03d}",
            evidence=(
                EvidenceItem(
                    description="Par de workloads",
                    value=f"{left} ↔ {right}",
                ),
                EvidenceItem(
                    description="Similaridade de cosseno",
                    value="0.990",
                ),
            ),
            analysis=(
                f"Os workloads `{left}` e `{right}` apresentam perfil de "
                "features estruturadas muito similar (cosseno 99.0%) no namespace."
            ),
            **template,
        )
        for idx, (left, right) in enumerate(
            (("app-a", "app-b"), ("app-c", "app-d"), ("app-e", "app-f")),
            start=1,
        )
    )

    groups = group_identical_res_findings(findings)
    assert len(groups) == 1
    assert len(groups[0]) == 3

    rendered = format_grouped_finding(groups[0])
    assert "| ID | Workload | Evidência |" in rendered
    assert "`ML-MLSIM-001`" in rendered
    assert "`ML-MLSIM-003`" in rendered
    assert rendered.count("**Recomendação:**") == 1
    assert "3 itens" in rendered
    assert "Investigar diferenças de tráfego." in rendered
