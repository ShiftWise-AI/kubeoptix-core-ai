#!/usr/bin/env python3
"""Benchmark reprodutível para sinais operacionais de logs."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.parsers.log import parse_pod_log

ASSESSMENT_ROOT = Path(__file__).resolve().parents[3] / "base-treinamento" / "assessment"

EXPECTED_SIGNALS = {
    "dns_lookup_failure": 1,
    "service_connectivity_failure": 1,
    "http_5xx": 1,
    "postgres_trust_auth": 1,
}


def iter_assessment_namespaces(root: Path | str | None = None) -> tuple[Path, ...]:
    base = Path(root) if root is not None else ASSESSMENT_ROOT
    if not base.exists():
        return ()
    namespaces = []
    for path in sorted(base.iterdir()):
        if path.is_dir() and (path / "apps").is_dir():
            namespaces.append(path)
    return tuple(namespaces)


def iter_log_files(root: Path | str | None = None) -> tuple[Path, ...]:
    namespaces = iter_assessment_namespaces(root)
    log_files: list[Path] = []
    for namespace_root in namespaces:
        log_files.extend(sorted(namespace_root.glob("apps/*/pod-logs/*.log")))
    return tuple(sorted(log_files))


def benchmark_namespace(namespace_root: Path) -> dict[str, int | float | str | dict[str, int]]:
    actual: dict[str, int] = {}
    for log_file in sorted(namespace_root.glob("apps/*/pod-logs/*.log")):
        summary = parse_pod_log(log_file, app_group=log_file.parent.parent.name)
        for signal in summary.runtime_signals:
            actual[signal] = actual.get(signal, 0) + 1

    true_positives = sum(min(actual.get(signal, 0), expected) for signal, expected in EXPECTED_SIGNALS.items())
    precision = true_positives / sum(actual.values()) if actual else 0.0
    recall = true_positives / sum(EXPECTED_SIGNALS.values()) if EXPECTED_SIGNALS else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "namespace": namespace_root.name,
        "expected": EXPECTED_SIGNALS,
        "actual": actual,
        "true_positives": true_positives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "files_analyzed": len(tuple(sorted(namespace_root.glob("apps/*/pod-logs/*.log")))),
    }


def benchmark(root: Path | str | None = None) -> dict[str, int | float | str | list[dict[str, int | float | str | dict[str, int]]]]:
    namespace_roots = iter_assessment_namespaces(root)
    namespace_results = [benchmark_namespace(ns_root) for ns_root in namespace_roots]
    total_files = sum(int(result["files_analyzed"]) for result in namespace_results)
    total_tp = sum(int(result["true_positives"]) for result in namespace_results)
    total_actual = {signal: 0 for signal in EXPECTED_SIGNALS}
    for result in namespace_results:
        for signal, count in result["actual"].items():
            total_actual[signal] = total_actual.get(signal, 0) + count

    precision = total_tp / sum(total_actual.values()) if total_actual else 0.0
    recall = total_tp / sum(EXPECTED_SIGNALS.values()) if EXPECTED_SIGNALS else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "namespaces": namespace_results,
        "files_analyzed": total_files,
        "true_positives": total_tp,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "expected": EXPECTED_SIGNALS,
        "actual": total_actual,
    }


def main() -> None:
    ns_results = iter_assessment_namespaces()
    if not ns_results:
        print("Nenhum namespace encontrado em base-treinamento/assessment.")
        return

    benchmark_result = benchmark()
    print(f"Namespaces avaliados: {len(ns_results)}")
    print(f"Arquivos analisados: {benchmark_result['files_analyzed']}")
    print(f"Sinais esperados: {benchmark_result['expected']}")
    print(f"Sinais detectados: {benchmark_result['actual']}")
    print(f"True positives: {benchmark_result['true_positives']}")
    print(f"Precision: {benchmark_result['precision']:.3f}")
    print(f"Recall: {benchmark_result['recall']:.3f}")
    print(f"F1: {benchmark_result['f1']:.3f}")
    for namespace in benchmark_result["namespaces"]:
        print(
            f"[{namespace['namespace']}] tp={namespace['true_positives']} "
            f"precision={namespace['precision']:.3f} recall={namespace['recall']:.3f} f1={namespace['f1']:.3f}"
        )


if __name__ == "__main__":
    main()
