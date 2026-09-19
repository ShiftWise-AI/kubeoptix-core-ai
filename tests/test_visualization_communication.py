"""Testes dos diagramas de comunicação."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.analysis.inventory import (
    _config_value_service_names,
    analyze_inventory,
    build_service_dependency_graph,
)
from kubeoptix_core_ai.config import AnalyzerConfig
from scripts.benchmark_log_signals import benchmark
from kubeoptix_core_ai.models.inventory import ConfigMapSpec, ServicePortSpec, ServiceSpec
from kubeoptix_core_ai.models.source import DataSourceRef
from kubeoptix_core_ai.models.workload import ContainerSpec, NamespaceWorkloadBundle, Workload
from kubeoptix_core_ai.parsers.log import parse_pod_log
from kubeoptix_core_ai.report.pipeline import AssessmentPipeline
from kubeoptix_core_ai.visualization.builders import build_all_visualizations
from kubeoptix_core_ai.visualization.datasets.communication import (
    build_external_communication_diagrams,
    build_external_dependencies_diagrams,
    build_internal_communication_diagrams,
)
from kubeoptix_core_ai.visualization.diagram_renderer import DiagramRenderer
from kubeoptix_core_ai.visualization.kubediagrams import (
    KubeDiagramsRenderer,
    manifest_index_for,
)
from kubeoptix_core_ai.visualization.kubediagrams.mapping import manifests_for_external_route
from kubeoptix_core_ai.visualization.models import VisualizationStatus
from kubeoptix_core_ai.visualization.png import PngRenderer

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_FRONTEND = "example-frontend"


@pytest.fixture
def three_tier_tree(tmp_path: Path) -> Path:
    """Namespace com 3 apps: frontend + 2 backends, cada um com route/service."""
    base = tmp_path / "metadados"
    ns = base / EXAMPLE_NAMESPACE

    apps = (
        ("backend-acesso-app", FIXTURES / "deployment_backend_acesso_app.yaml"),
        ("backend-acesso-batch", FIXTURES / "deployment_backend_acesso_app.yaml"),
        (EXAMPLE_FRONTEND, FIXTURES / "deployment_backend_acesso_app.yaml"),
    )
    for app_name, deployment_fixture in apps:
        app_dir = ns / "apps" / app_name
        (app_dir / "deployments").mkdir(parents=True)
        content = deployment_fixture.read_text(encoding="utf-8")
        content = content.replace("backend-acesso-app", app_name)
        (app_dir / "deployments" / f"{app_name}.yaml").write_text(content, encoding="utf-8")

        if app_name != EXAMPLE_FRONTEND:
            (app_dir / "services").mkdir(parents=True)
            svc = FIXTURES / "service_backend_acesso_app.yaml"
            svc_content = svc.read_text(encoding="utf-8").replace("backend-acesso-app", app_name)
            (app_dir / "services" / f"{app_name}.yaml").write_text(svc_content, encoding="utf-8")

            (app_dir / "routes").mkdir(parents=True)
            route = FIXTURES / "route_backend_acesso_app.yaml"
            route_content = route.read_text(encoding="utf-8").replace("backend-acesso-app", app_name)
            route_content = route_content.replace(
                "example-backend.apps.cluster.local",
                f"{app_name}.apps.cluster.local",
            )
            (app_dir / "routes" / f"{app_name}.yaml").write_text(route_content, encoding="utf-8")

            (app_dir / "pod-logs").mkdir(parents=True)
            log_line = (
                "DEBUG com.zaxxer.hikari.pool.HikariPool - "
                "Added connection oracle.jdbc.driver.T4CConnection@abc\n"
            )
            (app_dir / "pod-logs" / f"{app_name}-pod-1.log").write_text(log_line, encoding="utf-8")

    fe_dir = ns / "apps" / EXAMPLE_FRONTEND
    (fe_dir / "services").mkdir(parents=True)
    fe_svc = FIXTURES / "service_backend_acesso_app.yaml"
    fe_svc_content = (
        fe_svc.read_text(encoding="utf-8")
        .replace("backend-acesso-app", EXAMPLE_FRONTEND)
        .replace("8081", "8080")
    )
    (fe_dir / "services" / f"{EXAMPLE_FRONTEND}.yaml").write_text(
        fe_svc_content, encoding="utf-8"
    )
    (fe_dir / "routes").mkdir(parents=True)
    fe_route = FIXTURES / "route_backend_acesso_app.yaml"
    fe_route_content = (
        fe_route.read_text(encoding="utf-8")
        .replace("backend-acesso-app", EXAMPLE_FRONTEND)
        .replace("8081", "8080")
        .replace("example-backend.apps.cluster.local", "frontend.apps.cluster.local")
    )
    (fe_dir / "routes" / f"{EXAMPLE_FRONTEND}.yaml").write_text(
        fe_route_content, encoding="utf-8"
    )

    pods = ns / "resources" / "pods"
    pods.mkdir(parents=True)
    shutil.copy(FIXTURES / "pod_backend_acesso_app.yaml", pods / "pod.yaml")

    nodes = tmp_path / "worknodes"
    nodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", nodes / "osc3dv0117.yaml")
    return base


def test_parse_pod_log_detects_oracle_jdbc(tmp_path: Path) -> None:
    log_file = tmp_path / "backend-acesso-app-abc.log"
    log_file.write_text(
        "Added connection oracle.jdbc.driver.T4CConnection@deadbeef\n",
        encoding="utf-8",
    )
    summary = parse_pod_log(log_file, app_group="backend-acesso-app")
    assert "oracle.jdbc" in summary.runtime_signals


def test_parse_pod_log_detects_operational_failures(tmp_path: Path) -> None:
    dashboard_log = tmp_path / "kubeoptix-dashboard-0.log"
    dashboard_log.write_text(
        "API proxy error for http://analyzer-api:8000/reports/files: TypeError: fetch failed\n"
        "[cause]: Error: getaddrinfo ENOTFOUND analyzer-api\n"
        "10.217.0.67 - - [19/Sep/2026 11:17:43] \"GET /assessment/namespaces HTTP/1.1\" 500 -\n",
        encoding="utf-8",
    )
    dashboard_summary = parse_pod_log(dashboard_log, app_group="kubeoptix-dashboard")
    assert "dns_lookup_failure" in dashboard_summary.runtime_signals
    assert "http_5xx" in dashboard_summary.runtime_signals
    assert "service_connectivity_failure" in dashboard_summary.runtime_signals

    db_log = tmp_path / "kubeoptix-db-0.log"
    db_log.write_text(
        "initdb: warning: enabling \"trust\" authentication for local connections\n",
        encoding="utf-8",
    )
    db_summary = parse_pod_log(db_log, app_group="kubeoptix-db")
    assert "postgres_trust_auth" in db_summary.runtime_signals


def test_analyze_inventory_flags_unresolved_internal_service(tmp_path: Path) -> None:
    log_file = tmp_path / "kubeoptix-dashboard-0.log"
    log_file.write_text(
        "API proxy error for http://analyzer-api:8000/assessment/namespaces: TypeError: fetch failed\n"
        "[cause]: Error: getaddrinfo ENOTFOUND analyzer-api\n",
        encoding="utf-8",
    )
    service = ServiceSpec(
        name="analyzer-api",
        namespace="shiftwise-ai",
        service_type="ClusterIP",
        ports=(ServicePortSpec(name="http", port=8000, target_port=8000),),
        source=DataSourceRef(
            file_path=str(tmp_path / "analyzer-api.yaml"),
            resource_kind="Service",
            resource_name="analyzer-api",
            namespace="shiftwise-ai",
        ),
    )
    bundle = NamespaceWorkloadBundle(
        namespace="shiftwise-ai",
        workloads=(),
        services=(service,),
        routes=(),
        configmaps=(),
        operators=(),
        events=(),
        pod_logs=(parse_pod_log(log_file, app_group="kubeoptix-dashboard"),),
        secret_references=(),
    )
    ctx = AnalysisContext(bundle=bundle, nodes=())
    builder = FindingBuilder()
    analyze_inventory(ctx, builder)

    findings = builder.findings
    assert any(
        "analyzer-api" in finding.analysis.lower() and "dns" in finding.analysis.lower()
        for finding in findings
    )


def test_config_value_service_names_ignores_timezones_and_external_domains() -> None:
    assert _config_value_service_names("America/Sao_Paulo", key="TZ") == ()
    assert _config_value_service_names("https://api.vendor.example.com", key="API_URL") == ()
    assert _config_value_service_names("http://analyzer-api:8000", key="ANALYZER_API_URL") == ("analyzer-api",)
    assert _config_value_service_names("dashboard", key="API_HOST") == ("dashboard",)


def test_analyze_inventory_links_dns_failure_to_configured_service_dependency(tmp_path: Path) -> None:
    log_file = tmp_path / "kubeoptix-dashboard-0.log"
    log_file.write_text(
        "API proxy error for http://analyzer-api:8000/assessment/namespaces: TypeError: fetch failed\n"
        "[cause]: Error: getaddrinfo ENOTFOUND analyzer-api\n",
        encoding="utf-8",
    )
    service = ServiceSpec(
        name="analyzer-api",
        namespace="shiftwise-ai",
        service_type="ClusterIP",
        ports=(ServicePortSpec(name="http", port=8000, target_port=8000),),
        source=DataSourceRef(
            file_path=str(tmp_path / "analyzer-api.yaml"),
            resource_kind="Service",
            resource_name="analyzer-api",
            namespace="shiftwise-ai",
        ),
    )
    configmap = ConfigMapSpec(
        name="kubeoptix-dashboard-env",
        namespace="shiftwise-ai",
        app_group="kubeoptix-dashboard",
        keys=("ANALYZER_API_URL",),
        data={"ANALYZER_API_URL": "http://analyzer-api:8000"},
        source=DataSourceRef(
            file_path=str(tmp_path / "kubeoptix-dashboard-env.yaml"),
            resource_kind="ConfigMap",
            resource_name="kubeoptix-dashboard-env",
            namespace="shiftwise-ai",
        ),
    )
    workload = Workload(
        namespace="shiftwise-ai",
        name="kubeoptix-dashboard",
        app_group="kubeoptix-dashboard",
        kind="Deployment",
        referenced_configmaps=("kubeoptix-dashboard-env",),
        source=DataSourceRef(
            file_path=str(tmp_path / "kubeoptix-dashboard.yaml"),
            resource_kind="Deployment",
            resource_name="kubeoptix-dashboard",
            namespace="shiftwise-ai",
        ),
    )
    bundle = NamespaceWorkloadBundle(
        namespace="shiftwise-ai",
        workloads=(workload,),
        services=(service,),
        routes=(),
        configmaps=(configmap,),
        operators=(),
        events=(),
        pod_logs=(parse_pod_log(log_file, app_group="kubeoptix-dashboard"),),
        secret_references=(),
    )
    ctx = AnalysisContext(bundle=bundle, nodes=())
    builder = FindingBuilder()
    analyze_inventory(ctx, builder)

    findings = builder.findings
    assert any(
        "ConfigMap/env" in finding.analysis or "configmap/env" in finding.analysis.lower()
        for finding in findings
    )


def test_benchmark_handles_multiple_namespaces(tmp_path: Path) -> None:
    ns_a = tmp_path / "ns-a"
    ns_b = tmp_path / "ns-b"
    for namespace in (ns_a, ns_b):
        app_dir = namespace / "apps" / "demo-app"
        log_dir = app_dir / "pod-logs"
        log_dir.mkdir(parents=True)
        (log_dir / "demo-app-0.log").write_text(
            "INFO started\nTypeError: fetch failed\n[CAUSE] Error: getaddrinfo ENOTFOUND demo-api\n",
            encoding="utf-8",
        )

    result = benchmark(tmp_path)
    assert len(result["namespaces"]) == 2
    assert result["files_analyzed"] == 2
    assert result["precision"] >= 0.0
    assert result["recall"] >= 0.0


def test_analyze_inventory_flags_startup_guard_gap(tmp_path: Path) -> None:
    workload = Workload(
        namespace="shiftwise-ai",
        name="dashboard",
        app_group="dashboard",
        kind="Deployment",
        referenced_configmaps=("dashboard-env",),
        containers=(
            ContainerSpec(
                name="dashboard",
                image="nginx",
                source=DataSourceRef(
                    file_path=str(tmp_path / "dashboard.yaml"),
                    resource_kind="Deployment",
                    resource_name="dashboard",
                    namespace="shiftwise-ai",
                ),
            ),
        ),
        source=DataSourceRef(
            file_path=str(tmp_path / "dashboard.yaml"),
            resource_kind="Deployment",
            resource_name="dashboard",
            namespace="shiftwise-ai",
        ),
    )
    configmap = ConfigMapSpec(
        name="dashboard-env",
        namespace="shiftwise-ai",
        app_group="dashboard",
        keys=("API_URL",),
        data={"API_URL": "http://backend-api:8000"},
        source=DataSourceRef(
            file_path=str(tmp_path / "dashboard-env.yaml"),
            resource_kind="ConfigMap",
            resource_name="dashboard-env",
            namespace="shiftwise-ai",
        ),
    )
    bundle = NamespaceWorkloadBundle(
        namespace="shiftwise-ai",
        workloads=(workload,),
        services=(),
        routes=(),
        configmaps=(configmap,),
        operators=(),
        events=(),
        pod_logs=(),
        secret_references=(),
    )
    ctx = AnalysisContext(bundle=bundle, nodes=())
    builder = FindingBuilder()
    analyze_inventory(ctx, builder)

    assert any(
        "readinessProbe" in finding.analysis or "startupProbe" in finding.analysis
        for finding in builder.findings
    )


def test_build_service_dependency_graph_tracks_known_service_edges(tmp_path: Path) -> None:
    workload = Workload(
        namespace="shiftwise-ai",
        name="dashboard",
        app_group="dashboard",
        kind="Deployment",
        referenced_configmaps=("dashboard-env",),
        source=DataSourceRef(
            file_path=str(tmp_path / "dashboard.yaml"),
            resource_kind="Deployment",
            resource_name="dashboard",
            namespace="shiftwise-ai",
        ),
    )
    service = ServiceSpec(
        name="analyzer-api",
        namespace="shiftwise-ai",
        service_type="ClusterIP",
        ports=(ServicePortSpec(name="http", port=8000),),
        source=DataSourceRef(
            file_path=str(tmp_path / "analyzer-api.yaml"),
            resource_kind="Service",
            resource_name="analyzer-api",
            namespace="shiftwise-ai",
        ),
    )
    configmap = ConfigMapSpec(
        name="dashboard-env",
        namespace="shiftwise-ai",
        app_group="dashboard",
        keys=("ANALYZER_API_URL",),
        data={"ANALYZER_API_URL": "http://analyzer-api:8000"},
        source=DataSourceRef(
            file_path=str(tmp_path / "dashboard-env.yaml"),
            resource_kind="ConfigMap",
            resource_name="dashboard-env",
            namespace="shiftwise-ai",
        ),
    )
    bundle = NamespaceWorkloadBundle(
        namespace="shiftwise-ai",
        workloads=(workload,),
        services=(service,),
        routes=(),
        configmaps=(configmap,),
        operators=(),
        events=(),
        pod_logs=(),
        secret_references=(),
    )

    graph = build_service_dependency_graph(bundle)
    assert ("dashboard", "analyzer-api", "config:dashboard-env") in graph


def test_external_diagrams_split_per_route(three_tier_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=three_tier_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    diagrams = build_external_communication_diagrams(bundle)

    assert len(diagrams) == 3
    titles = {d.title for d in diagrams}
    assert "Comunicação externa — backend-acesso-app" in titles
    assert f"Comunicação externa — {EXAMPLE_FRONTEND}" in titles

    for diagram in diagrams:
        node_types = {n.node_type for n in diagram.nodes}
        assert "route" in node_types
        assert "service" in node_types
        assert "workload" in node_types


def test_internal_diagrams_split_per_service(three_tier_tree: Path, tmp_path: Path) -> None:
    config = AnalyzerConfig(
        workloads_base=three_tier_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    diagrams = build_internal_communication_diagrams(bundle)

    assert len(diagrams) == 3
    for diagram in diagrams:
        workload_nodes = [n for n in diagram.nodes if n.node_type == "workload"]
        assert len(workload_nodes) == 1


def test_external_dependencies_include_oracle_and_registry(
    three_tier_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=three_tier_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    diagrams = build_external_dependencies_diagrams(bundle)

    backend_diagrams = [d for d in diagrams if "backend-acesso" in d.title]
    assert len(backend_diagrams) == 2
    for diagram in backend_diagrams:
        edge_types = {e.edge_type for e in diagram.edges}
        assert "image_pull" in edge_types
        assert "database" in edge_types

    frontend_diagram = next(d for d in diagrams if d.title.endswith("frontend"))
    frontend_edge_types = {e.edge_type for e in frontend_diagram.edges}
    assert "image_pull" in frontend_edge_types
    assert "database" not in frontend_edge_types


def test_no_frontend_to_backend_edge_in_diagrams(
    three_tier_tree: Path, tmp_path: Path
) -> None:
    config = AnalyzerConfig(
        workloads_base=three_tier_tree,
        worknodes_path=tmp_path / "worknodes",
    )
    bundle = AssessmentPipeline(config).run(EXAMPLE_NAMESPACE)
    index = manifest_index_for(bundle)
    assets_dir = tmp_path / "comm_assets"
    png_renderer = PngRenderer(assets_dir, path_prefix="comm_assets")
    diagram_renderer = DiagramRenderer(
        KubeDiagramsRenderer(assets_dir, namespace=EXAMPLE_NAMESPACE, path_prefix="comm_assets"),
        png_renderer,
        manifest_index=index,
    )
    viz = build_all_visualizations(
        bundle,
        renderer=png_renderer,
        diagram_renderer=diagram_renderer,
    )

    comm_viz = [
        v
        for v in viz.visualizations
        if v.section.startswith("communication_") and v.status == VisualizationStatus.AVAILABLE
    ]
    for v in comm_viz:
        assert v.image_relpath
        assert v.yaml_sources

    internal = build_internal_communication_diagrams(bundle)
    for diagram in internal:
        edge_pairs = {(edge.source_id, edge.target_id) for edge in diagram.edges}
        assert ("wl_example-frontend", "wl_backend") not in edge_pairs
        assert ("wl_example_frontend", "wl_backend") not in edge_pairs
