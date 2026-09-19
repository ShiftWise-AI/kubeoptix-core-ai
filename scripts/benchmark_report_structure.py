#!/usr/bin/env python3
"""Benchmark de paridade estrutural do relatório Markdown."""

from __future__ import annotations

import argparse
from pathlib import Path

EXPECTED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("## 1. Sumário executivo", "sumário executivo"),
    ("## 2. Inventário do namespace / aplicações", "inventário do namespace"),
    ("## 3. Arquitetura reversa", "arquitetura reversa"),
    ("## 4. Recursos de CPU e memória", "recursos de CPU e memória"),
    ("## 5. Observabilidade (métricas, logs, monitoramento)", "observabilidade"),
    ("## 6. ConfigMaps e dados sensíveis (secrets, chaves, certificados)", "configmaps e dados sensíveis"),
    ("## 7. Plano de ação", "plano de ação"),
    ("## 8. Referências utilizadas", "referências utilizadas"),
)


def _default_reports_root() -> Path:
    return Path(__file__).resolve().parents[3] / "base-treinamento" / "reports"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def benchmark_report_structure(generated_path: Path, reference_path: Path) -> dict[str, object]:
    generated = _read_text(generated_path)
    reference = _read_text(reference_path)

    hit_count = 0
    missing: list[str] = []
    for heading, label in EXPECTED_SECTIONS:
        if heading in generated:
            hit_count += 1
        else:
            missing.append(label)

    architecture_ok = (
        "## 3. Arquitetura reversa" in generated
        and (
            "Arquitetura reversa (fallback textual)" in generated
            or "Fluxo de entrada, Service e dependências internas" in generated
            or "Diagrama gerado a partir dos manifests YAML" in generated
        )
    )
    fallback_ok = "fallback textual" in generated.lower() or "Fluxo de entrada, Service e dependências internas" in generated
    reference_has_required_structure = all(heading in reference for heading, _ in EXPECTED_SECTIONS)

    score = (hit_count / len(EXPECTED_SECTIONS)) if EXPECTED_SECTIONS else 1.0
    return {
        "generated": str(generated_path),
        "reference": str(reference_path),
        "structure_score": score,
        "sections_found": hit_count,
        "sections_expected": len(EXPECTED_SECTIONS),
        "missing_sections": missing,
        "architecture_ok": architecture_ok,
        "fallback_ok": fallback_ok,
        "reference_has_required_structure": reference_has_required_structure,
    }


def _print_summary(metrics: dict[str, object]) -> None:
    score = float(metrics["structure_score"])
    print(f"Relatório gerado: {metrics['generated']}")
    print(f"Relatório de referência: {metrics['reference']}")
    print(
        "Estrutura do relatório: "
        f"{metrics['sections_found']}/{metrics['sections_expected']} ({score:.2%})"
    )
    print(f"Arquitetura reversa presente: {metrics['architecture_ok']}")
    print(f"Fallback textual presente: {metrics['fallback_ok']}")
    print(f"Estrutura esperada no arquivo de referência: {metrics['reference_has_required_structure']}")
    if metrics["missing_sections"]:
        print("Seções ausentes: " + ", ".join(metrics["missing_sections"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_reports = _default_reports_root()
    parser.add_argument(
        "--generated",
        type=Path,
        default=default_reports / "shiftwise-ai.md",
        help="Arquivo Markdown produzido pelo kubeoptix-core-ai.",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=default_reports / "shiftwise-ai-llm.md",
        help="Arquivo Markdown de referência do kubeoptix-analyzer.",
    )
    args = parser.parse_args()

    metrics = benchmark_report_structure(args.generated, args.reference)
    _print_summary(metrics)


if __name__ == "__main__":
    main()
