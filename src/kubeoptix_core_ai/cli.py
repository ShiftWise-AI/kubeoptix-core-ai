"""Command-line interface for KubeOptix Core AI."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from kubeoptix_core_ai import __version__
from kubeoptix_core_ai.analysis.engine import AnalysisEngine
from kubeoptix_core_ai.analysis.report import print_analysis_report
from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.diagnostic.report import print_diagnostic_report
from kubeoptix_core_ai.diagnostic.runner import DiagnosticRunner
from kubeoptix_core_ai.discovery.scanner import list_namespace_dirs
from kubeoptix_core_ai.errors import AnalyzerError, ConfigurationError
from kubeoptix_core_ai.loaders.workload_loader import WorkloadLoader
from kubeoptix_core_ai.loaders.worknode_loader import WorknodeLoader
from kubeoptix_core_ai.logging import setup_logging
from kubeoptix_core_ai.report.markdown import write_assessment_report
from kubeoptix_core_ai.report.i18n import resolve_system_locale
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline


def _workload_to_dict(workload) -> dict:
    """Serialize a workload to JSON output, including traceability."""
    return json.loads(workload.model_dump_json())


def _node_to_dict(node) -> dict:
    return json.loads(node.model_dump_json())


def cmd_list_namespaces(config: AnalyzerConfig) -> int:
    namespaces = [p.name for p in list_namespace_dirs(config.workloads_base)]
    for ns in namespaces:
        print(ns)
    return 0


def cmd_load_workloads(config: AnalyzerConfig, namespace: str, output_json: bool) -> int:
    loader = WorkloadLoader(config)
    bundle = loader.load_namespace(namespace)

    if output_json:
        payload = {
            "namespace": bundle.namespace,
            "workload_count": bundle.workload_count,
            "parse_errors": list(bundle.parse_errors),
            "workloads": [_workload_to_dict(w) for w in bundle.workloads],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Namespace: {bundle.namespace}")
        print(f"Workloads carregados: {bundle.workload_count}")
        if bundle.parse_errors:
            print(f"Avisos de parsing: {len(bundle.parse_errors)}")
        for workload in bundle.workloads:
            cpu = workload.total_cpu_request_per_pod_millicores
            mem = workload.total_memory_request_per_pod_bytes
            print(
                f"  - {workload.name} "
                f"(réplicas={workload.replicas_desired}, "
                f"QoS={workload.qos_class}, "
                f"cpu_req/pod={cpu}m, "
                f"placements={len(workload.placements)}, "
                f"metrics={len(workload.metrics)}) "
                f"[origem: {workload.source.file_path}]"
            )
    return 0


def cmd_load_worknodes(config: AnalyzerConfig, output_json: bool) -> int:
    loader = WorknodeLoader(config)
    bundle = loader.load()

    if output_json:
        payload = {
            "node_count": bundle.node_count,
            "parse_errors": list(bundle.parse_errors),
            "nodes": [_node_to_dict(n) for n in bundle.nodes],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Worknodes carregados: {bundle.node_count}")
        if bundle.parse_errors:
            print(f"Avisos de parsing: {len(bundle.parse_errors)}")
        for node in bundle.nodes:
            cpu_alloc = node.cpu_allocatable.raw if node.cpu_allocatable else "N/A"
            mem_alloc = node.memory_allocatable.raw if node.memory_allocatable else "N/A"
            print(
                f"  - {node.name} "
                f"(role={node.role}, env={node.env}, "
                f"cpu_alloc={cpu_alloc}, mem_alloc={mem_alloc}) "
                f"[origem: {node.source.file_path}]"
            )
    return 0


def cmd_report(
    config: AnalyzerConfig,
    namespace: str,
    output_dir: Path,
    *,
    enable_ml: bool = True,
    ml_seed: int | None = None,
) -> Path:
    locale = resolve_system_locale()
    ml_config = _ml_config_from_flags(enable_ml=enable_ml, ml_seed=ml_seed)

    pipeline = AssessmentPipeline(config, ml_config=ml_config)
    bundle = pipeline.run(namespace, enable_ml=enable_ml)
    path = write_assessment_report(bundle, output_dir, locale=locale)
    print(f"Relatório gerado: {path}")
    print(
        f"  Workloads: {bundle.analysis.workloads_analyzed}, "
        f"Findings: {bundle.analysis.finding_count}"
    )
    return path


def cmd_run(
    config: AnalyzerConfig,
    output_dir: Path,
    *,
    enable_ml: bool = True,
    ml_seed: int | None = None,
) -> int:
    namespaces = [p.name for p in list_namespace_dirs(config.workloads_base)]
    if not namespaces:
        raise ConfigurationError(
            f"Nenhum namespace encontrado em: {config.workloads_base}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    for namespace in namespaces:
        cmd_report(
            config,
            namespace,
            output_dir,
            enable_ml=enable_ml,
            ml_seed=ml_seed,
        )
    return 0


def _ml_config_from_flags(
    *,
    enable_ml: bool,
    ml_seed: int | None,
):
    if ml_seed is not None:
        from kubeoptix_core_ai.ml.config import MLConfig

        return MLConfig(enabled=enable_ml, random_seed=ml_seed)
    if not enable_ml:
        from kubeoptix_core_ai.ml.config import MLConfig

        return MLConfig(enabled=False)
    return None


def cmd_analyze(
    config: AnalyzerConfig,
    namespace: str,
    output_json: bool,
    *,
    enable_ml: bool = True,
    ml_seed: int | None = None,
) -> int:
    ml_config = _ml_config_from_flags(enable_ml=enable_ml, ml_seed=ml_seed)

    engine = AnalysisEngine(config, ml_config=ml_config)
    report = engine.analyze_namespace(namespace, enable_ml=enable_ml)

    if output_json:
        print(report.model_dump_json(indent=2))
    else:
        print_analysis_report(report)
    return 0


def cmd_diagnose(config: AnalyzerConfig, namespace: str, output_json: bool) -> int:
    runner = DiagnosticRunner(config)
    report = runner.run(namespace)

    if output_json:
        print(report.model_dump_json(indent=2))
    else:
        print_diagnostic_report(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kubeoptix-core-ai",
        description="Agente local de análise de workloads OpenShift/Kubernetes",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        help="Diretório raiz dos metadados (namespaces + worknodes)",
    )
    parser.add_argument(
        "--workloads-base",
        type=Path,
        help="Diretório base dos metadados de namespaces",
    )
    parser.add_argument(
        "--worknodes-path",
        type=Path,
        help="Diretório dos arquivos YAML de worknodes",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Ativa logging detalhado",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Saída em JSON",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-namespaces", help="Lista namespaces disponíveis")

    load_wl = subparsers.add_parser(
        "load-workloads",
        help="Carrega workloads de um namespace",
    )
    load_wl.add_argument(
        "--namespace",
        required=True,
        help="Nome do namespace (ex.: meu-namespace-prd)",
    )

    subparsers.add_parser("load-worknodes", help="Carrega worknodes do cluster")

    diagnose = subparsers.add_parser(
        "diagnose",
        help="Diagnóstico de ingestão e normalização (sem relatório final)",
    )
    diagnose.add_argument(
        "--namespace",
        required=True,
        help="Nome do namespace (ex.: meu-namespace-prd)",
    )

    analyze = subparsers.add_parser(
        "analyze",
        help="Análise de workloads (determinística + ML local opcional)",
    )
    analyze.add_argument(
        "--namespace",
        required=True,
        help="Nome do namespace (ex.: meu-namespace-prd)",
    )
    analyze.add_argument(
        "--no-ml",
        action="store_true",
        help="Desativa a camada estatística / ML local",
    )
    analyze.add_argument(
        "--ml-seed",
        type=int,
        default=None,
        help="Seed para algoritmos estocásticos (K-Means, Isolation Forest)",
    )

    report = subparsers.add_parser(
        "report",
        help="Gera relatório Markdown de assessment",
    )
    report.add_argument(
        "--namespace",
        required=True,
        help="Nome do namespace (ex.: meu-namespace-prd)",
    )
    report.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Diretório de saída (padrão: output/)",
    )
    report.add_argument(
        "--no-ml",
        action="store_true",
        help="Desativa a camada estatística / ML local",
    )
    report.add_argument(
        "--ml-seed",
        type=int,
        default=None,
        help="Seed para algoritmos estocásticos (K-Means, Isolation Forest)",
    )

    run = subparsers.add_parser(
        "run",
        help="Gera relatórios Markdown para todos os namespaces nos metadados",
    )
    run.add_argument(
        "--metadata-dir",
        type=Path,
        required=True,
        help="Diretório raiz dos metadados (namespaces + worknodes)",
    )
    run.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Diretório de saída dos relatórios .md",
    )
    run.add_argument(
        "--no-ml",
        action="store_true",
        help="Desativa a camada estatística / ML local",
    )
    run.add_argument(
        "--ml-seed",
        type=int,
        default=None,
        help="Seed para algoritmos estocásticos (K-Means, Isolation Forest)",
    )

    return parser


def _resolve_config(args: argparse.Namespace) -> AnalyzerConfig:
    metadata_dir = getattr(args, "metadata_dir", None)
    if metadata_dir:
        return AnalyzerConfig.from_metadata_dir(metadata_dir)

    config = AnalyzerConfig.from_env()
    if args.workloads_base or args.worknodes_path:
        return AnalyzerConfig(
            workloads_base=args.workloads_base or config.workloads_base,
            worknodes_path=args.worknodes_path or config.worknodes_path,
        )
    return config


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level)

    config = _resolve_config(args)

    try:
        if args.command == "list-namespaces":
            return cmd_list_namespaces(config)
        if args.command == "load-workloads":
            return cmd_load_workloads(config, args.namespace, args.json)
        if args.command == "load-worknodes":
            return cmd_load_worknodes(config, args.json)
        if args.command == "diagnose":
            return cmd_diagnose(config, args.namespace, args.json)
        if args.command == "analyze":
            return cmd_analyze(
                config,
                args.namespace,
                args.json,
                enable_ml=not args.no_ml,
                ml_seed=args.ml_seed,
            )
        if args.command == "report":
            cmd_report(
                config,
                args.namespace,
                args.output,
                enable_ml=not args.no_ml,
                ml_seed=args.ml_seed,
            )
            return 0
        if args.command == "run":
            return cmd_run(
                config,
                args.output,
                enable_ml=not args.no_ml,
                ml_seed=args.ml_seed,
            )
    except ConfigurationError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2
    except AnalyzerError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
