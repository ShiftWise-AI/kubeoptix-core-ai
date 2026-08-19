"""Gerador de relatório de assessment em Markdown (pt-BR).

Produz documento estruturado a partir exclusivamente dos dados ingeridos e
dos findings gerados — sem inventar métricas, rotas, logs ou eventos ausentes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from kubeoptix_core_ai.analysis.helpers import (
    aggregate_runtime_usage,
    derive_scheduling_pool_selector,
    format_cpu_millicores,
    format_memory_bytes,
    has_pod_anti_affinity,
    matching_nodes,
    node_role_label,
    pool_cpu_allocatable_millicores,
    pool_memory_allocatable_bytes,
)
from kubeoptix_core_ai.models.finding import AnalysisReport, Finding, Severity
from kubeoptix_core_ai.models.inventory import (
    ConfigMapSpec,
    OperatorCSVSpec,
    PodLogSummary,
    RouteSpec,
    SecretReference,
    ServiceSpec,
)
from kubeoptix_core_ai.models.node import WorkNode
from kubeoptix_core_ai.models.workload import Workload
from kubeoptix_core_ai.report.finding_groups import (
    finding_section_ids,
    format_grouped_finding,
    group_identical_res_findings,
)
from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.datasets.architecture import (
    build_namespace_architecture_diagram,
)
from kubeoptix_core_ai.visualization.diagram_renderer import DiagramRenderer
from kubeoptix_core_ai.visualization.kubediagrams.mapping import manifests_for_namespace_architecture
from kubeoptix_core_ai.visualization.markdown import (
    _markdown_image,
    embed_markdown_images,
    render_section_visualizations,
)
from kubeoptix_core_ai.visualization.pipeline import (
    VisualizationPipeline,
    create_renderers,
    report_assets_prefix,
)
REPORT_FILE_ENCODING = "utf-8"
REPORT_FILE_LANGUAGE = "pt-BR"

_ML_CATEGORIES = frozenset({"MLSTAT", "MLCOMP", "MLANOM", "MLCLUST", "MLSIM"})
_SECTION_CATEGORIES: dict[str, tuple[str, ...]] = {
    "cpu": ("CPU", "RES"),
    "memory": ("MEM",),
    "qos": ("QOS",),
    "replicas": ("REPLICA",),
    "probes": ("PROBE",),
    "scheduling": ("SCHED",),
    "storage": ("STORAGE",),
    "workload_node": ("WNODE",),
    "inventory": ("ROUTE", "CONFIG", "LOG", "OPER"),
    "anomalies": tuple(_ML_CATEGORIES),
}

_FINDING_CATEGORY_LEGEND: tuple[tuple[str, str], ...] = (
    ("CPU", "Dimensionamento e uso de CPU"),
    ("MEM", "Dimensionamento e uso de memória"),
    ("RES", "Recursos declarados (request/limit gerais)"),
    ("QOS", "Quality of Service — classes Guaranteed, Burstable e BestEffort"),
    ("REPLICA", "Réplicas, HPA e disponibilidade"),
    ("PROBE", "Liveness, readiness e startup probes"),
    ("SCHED", "Scheduling, affinity e distribuição de pods"),
    ("STORAGE", "Volumes persistentes e PVCs"),
    ("WNODE", "Correlação workload × worknode"),
    ("ROUTE", "Routes e exposição HTTP/TLS"),
    ("CONFIG", "ConfigMaps e configuração"),
    ("LOG", "Logs coletados dos pods"),
    ("OPER", "Operadores (OLM/CSV)"),
    ("MLSTAT", "Sinais estatísticos locais"),
    ("MLCOMP", "Comparação estatística entre workloads"),
    ("MLANOM", "Detecção de anomalias estatísticas"),
    ("MLCLUST", "Agrupamento (clustering) de workloads"),
    ("MLSIM", "Similaridade entre workloads"),
)

_SEVERITY_LEGEND: tuple[tuple[str, str], ...] = (
    ("CRITICAL", "Risco imediato ou impacto operacional grave"),
    ("HIGH", "Problema significativo que requer atenção prioritária"),
    ("MEDIUM", "Desvio relevante; planejar correção"),
    ("LOW", "Oportunidade de melhoria ou risco residual baixo"),
    ("INFO", "Informativo; sem ação obrigatória"),
)

_CONFIDENCE_LEGEND: tuple[tuple[str, str], ...] = (
    ("HIGH", "Evidência direta nos artefatos coletados"),
    ("MEDIUM", "Inferência com suporte parcial nos dados"),
    ("LOW", "Hipótese com evidência limitada"),
)

_TECHNICAL_ACRONYMS: tuple[tuple[str, str], ...] = (
    ("HPA", "Horizontal Pod Autoscaler"),
    ("QoS", "Quality of Service — classe de garantia de recursos do pod"),
    ("PVC", "PersistentVolumeClaim"),
    ("TLS", "Transport Layer Security"),
    ("RES-*", "Prefixo dos IDs de findings determinísticos (ex.: `RES-CPU-001`)"),
    ("ML-*", "Prefixo dos IDs de findings da camada estatística (ex.: `ML-MLANOM-001`)"),
    ("PodMetrics", "Métricas de runtime coletadas via API `metrics.k8s.io`"),
)

_REDHAT_TECHNICAL_DOCUMENTATION: tuple[tuple[str, str, str], ...] = (
    (
        "Visão geral de workloads",
        "Red Hat OpenShift — Gerenciamento de workloads",
        "https://docs.openshift.com/container-platform/latest/nodes/pods/nodes-pods-resource-limits.html",
    ),
    (
        "CPU e memória (requests/limits)",
        "Red Hat OpenShift — Recursos de computação para scheduling",
        "https://docs.openshift.com/container-platform/latest/nodes/scheduling/nodes-scheduler-compute-resources.html",
    ),
    (
        "QoS e overcommit",
        "Red Hat OpenShift — Overcommit de recursos no cluster",
        "https://docs.openshift.com/container-platform/latest/nodes/clusters/nodes-cluster-overcommit.html",
    ),
    (
        "Probes (liveness, readiness, startup)",
        "Red Hat OpenShift — Monitoramento de saúde de aplicações",
        "https://docs.openshift.com/container-platform/latest/applications/application-health.html",
    ),
    (
        "Scheduling e placement",
        "Red Hat OpenShift — Sobre o scheduler de Pods",
        "https://docs.openshift.com/container-platform/latest/nodes/scheduling/nodes-scheduler-about.html",
    ),
    (
        "HPA e réplicas",
        "Red Hat OpenShift — Autoscaling de Pods",
        "https://docs.openshift.com/container-platform/latest/nodes/pods/nodes-pods-autoscaling.html",
    ),
    (
        "Monitoramento e métricas",
        "Red Hat OpenShift — Visão geral de monitoramento",
        "https://docs.openshift.com/container-platform/latest/monitoring/monitoring-overview.html",
    ),
    (
        "Storage e PVCs",
        "Red Hat OpenShift — Armazenamento persistente",
        "https://docs.openshift.com/container-platform/latest/storage/understanding-persistent-storage.html",
    ),
    (
        "Routes e TLS",
        "Red Hat OpenShift — Configuração de Routes",
        "https://docs.openshift.com/container-platform/latest/networking/routes/route-configuration.html",
    ),
    (
        "Operadores (OLM)",
        "Red Hat OpenShift — Operator Lifecycle Manager (OLM)",
        "https://docs.openshift.com/container-platform/latest/operators/understanding/olm-understanding-olm.html",
    ),
    (
        "ConfigMaps",
        "Red Hat OpenShift — ConfigMaps em aplicações",
        "https://docs.openshift.com/container-platform/latest/builds/building-applications.html#builds-buildconfig-maps_building-applications",
    ),
)

_SUPPLEMENTARY_TECHNICAL_DOCUMENTATION: tuple[tuple[str, str, str], ...] = (
    (
        "Métricas de runtime (PodMetrics)",
        "Kubernetes — Pipeline de métricas de recursos",
        "https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/",
    ),
    (
        "Referência upstream de recursos",
        "Kubernetes — Gerenciamento de recursos de Pods e containers",
        "https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/",
    ),
)

_REDHAT_BIBLIOGRAPHIC_REFERENCES: tuple[tuple[str, str], ...] = (
    (
        "Red Hat, Inc. *Red Hat OpenShift Container Platform — "
        "Documentação oficial.* docs.openshift.com.",
        "Referência primária para operação, networking, operadores e workloads.",
    ),
    (
        "Duncan, C.; Mier, T.; Brindley, A. *OpenShift for Developers.* "
        "O'Reilly Media, 2ª ed., 2021.",
        "Desenvolvimento e operação de aplicações em OpenShift.",
    ),
    (
        "Ibsen, R.; Schimanski, M. *Kubernetes Patterns.* "
        "O'Reilly Media, 2ª ed., 2020.",
        "Padrões de design para workloads em plataformas Kubernetes/OpenShift.",
    ),
    (
        "Red Hat, Inc. *OpenShift Container Platform — "
        "Scalability and Performance Guide.* docs.openshift.com.",
        "Dimensionamento de recursos, réplicas e capacidade de cluster.",
    ),
)

_SUPPLEMENTARY_BIBLIOGRAPHIC_REFERENCES: tuple[tuple[str, str], ...] = (
    (
        "Beyer, B. et al. *Site Reliability Engineering: How Google Runs "
        "Production Systems.* O'Reilly Media, 2016.",
        "Práticas complementares de confiabilidade e observabilidade.",
    ),
    (
        "Burns, B.; Grant, B.; Oppenheimer, D.; Brewer, E.; Wilkes, J. "
        "*Borg, Omega, and Kubernetes.* ACM Queue, 14(1), 2016.",
        "Contexto histórico de orquestração em larga escala.",
    ),
)


def _relative_path(path: str, base: Path) -> str:
    try:
        return str(Path(path).relative_to(base))
    except ValueError:
        return path


def _format_usage_cpu(qty: object) -> str:
    from kubeoptix_core_ai.models.quantities import ResourceQuantity

    if isinstance(qty, ResourceQuantity):
        return format_cpu_millicores(qty.normalized_value)
    return "—"


def _format_usage_memory(qty: object) -> str:
    from kubeoptix_core_ai.models.quantities import ResourceQuantity

    if isinstance(qty, ResourceQuantity):
        return format_memory_bytes(qty.normalized_value)
    return "—"


def _pool_summary(
    nodes: tuple[WorkNode, ...],
    workloads: tuple[Workload, ...],
) -> tuple[dict[str, str], tuple[WorkNode, ...], str]:
    selector = derive_scheduling_pool_selector(workloads)
    pool_nodes = matching_nodes(nodes, selector)
    if selector:
        desc = ", ".join(f"{k}={v}" for k, v in sorted(selector.items()))
    else:
        desc = "todos os nós coletados"
    return selector, pool_nodes, desc


def _node_by_name(nodes: tuple[WorkNode, ...]) -> dict[str, WorkNode]:
    return {n.name: n for n in nodes}


def _md_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return "_Nenhum dado disponível._\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    return "\n".join(lines) + "\n"


def _probe_summary(workload: Workload) -> str:
    if not workload.containers:
        return "Nenhuma"
    parts: list[str] = []
    for c in workload.containers:
        probes: list[str] = []
        if c.readiness_probe:
            probes.append("readiness")
        if c.liveness_probe:
            probes.append("liveness")
        if c.startup_probe:
            probes.append("startup")
        if probes:
            parts.append(f"{c.name}: {', '.join(probes)}")
    return "; ".join(parts) if parts else "Nenhuma"


def _selector_summary(workload: Workload) -> str:
    if not workload.node_selector:
        return "—"
    return ", ".join(f"{k}={v}" for k, v in sorted(workload.node_selector.items()))


def _affinity_summary(workload: Workload) -> str:
    if has_pod_anti_affinity(workload):
        return "podAntiAffinity"
    if workload.affinity:
        return "affinity configurada"
    return "Nenhuma"


def _hpa_summary(workload: Workload) -> str:
    parts: list[str] = []
    if workload.hpa is not None:
        hpa_parts: list[str] = []
        if workload.hpa.min_replicas is not None:
            hpa_parts.append(f"min={workload.hpa.min_replicas}")
        if workload.hpa.max_replicas is not None:
            hpa_parts.append(f"max={workload.hpa.max_replicas}")
        if workload.hpa.metrics:
            hpa_parts.append(f"métricas: {', '.join(workload.hpa.metrics)}")
        parts.append("HPA: " + (", ".join(hpa_parts) if hpa_parts else workload.hpa.name))
    if workload.vpa is not None:
        mode = workload.vpa.update_mode or "—"
        parts.append(f"VPA: {workload.vpa.name} (mode={mode})")
    return "; ".join(parts) if parts else "—"


def _pdb_summary(workload: Workload) -> str:
    if workload.pdb is None:
        return "—"
    parts: list[str] = [workload.pdb.name]
    if workload.pdb.min_available is not None:
        parts.append(f"minAvailable={workload.pdb.min_available}")
    if workload.pdb.max_unavailable is not None:
        parts.append(f"maxUnavailable={workload.pdb.max_unavailable}")
    return ", ".join(parts)


def _update_strategy_summary(workload: Workload) -> str:
    if workload.update_strategy:
        return workload.update_strategy
    if workload.kind == "CronJob" and workload.schedule:
        return f"schedule={workload.schedule}"
    return "—"


def _container_cpu_limit_m(workload: Workload) -> str:
    total = 0.0
    has_any = False
    for c in workload.containers:
        if c.cpu_limit is not None:
            total += c.cpu_limit.normalized_value
            has_any = True
    return format_cpu_millicores(total) if has_any else "—"


def _container_mem_limit(workload: Workload) -> str:
    total = 0.0
    has_any = False
    for c in workload.containers:
        if c.memory_limit is not None:
            total += c.memory_limit.normalized_value
            has_any = True
    return format_memory_bytes(total) if has_any else "—"


def _container_cpu_request_m(workload: Workload) -> str:
    if workload.total_cpu_request_per_pod_millicores is None:
        return "—"
    return format_cpu_millicores(workload.total_cpu_request_per_pod_millicores)


def _container_mem_request(workload: Workload) -> str:
    if workload.total_memory_request_per_pod_bytes is None:
        return "—"
    return format_memory_bytes(workload.total_memory_request_per_pod_bytes)


def _replicas_display(workload: Workload) -> str:
    desired = workload.replicas_desired
    ready = workload.replicas_ready
    if desired is None and ready is None:
        return "—"
    if ready is None:
        return str(desired)
    return f"{desired}/{ready}"


def _workloads_table(workloads: tuple[Workload, ...]) -> str:
    rows: list[tuple[str, ...]] = []
    for wl in workloads:
        config_refs = ", ".join(wl.referenced_configmaps) or "—"
        secret_refs = ", ".join(wl.referenced_secrets) or "—"
        pod_count = str(len(wl.placements)) if wl.placements else "—"
        rows.append(
            (
                f"`{wl.name}`",
                wl.kind,
                _replicas_display(wl),
                pod_count,
                wl.qos_class or "—",
                _container_cpu_request_m(wl),
                _container_cpu_limit_m(wl),
                _container_mem_request(wl),
                _container_mem_limit(wl),
                _hpa_summary(wl),
                _pdb_summary(wl),
                _probe_summary(wl),
                _update_strategy_summary(wl),
                config_refs,
                secret_refs,
                _selector_summary(wl),
                _affinity_summary(wl),
            )
        )
    return _md_table(
        (
            "Workload",
            "Controller",
            "Réplicas (desej./prontas)",
            "Pods",
            "QoS",
            "CPU request/pod",
            "CPU limit/pod",
            "Mem request/pod",
            "Mem limit/pod",
            "Autoscaling",
            "PDB",
            "Probes",
            "Estratégia/Schedule",
            "ConfigMaps",
            "Secrets",
            "Node selector",
            "Afinidade",
        ),
        rows,
    )


def _placement_table(
    workloads: tuple[Workload, ...],
    nodes: tuple[WorkNode, ...],
) -> str:
    node_map = _node_by_name(nodes)
    rows: list[tuple[str, ...]] = []
    for wl in workloads:
        for placement in wl.placements:
            node = node_map.get(placement.node_name or "")
            role = node_role_label(node) if node else "—"
            rows.append(
                (
                    f"`{placement.pod_name}`",
                    f"`{wl.name}`",
                    placement.node_name or "—",
                    role,
                    placement.qos_class or "—",
                )
            )
    if not rows:
        return (
            "Informação de placement não disponível nos dados coletados "
            "(arquivos de Pod ausentes ou sem `status.hostIP`/`spec.nodeName`).\n"
        )
    return _md_table(
        ("Pod", "Workload", "Nó", "Papel do nó", "QoS (pod)"),
        rows,
    )


def _runtime_metrics_table(workloads: tuple[Workload, ...]) -> str:
    """Tabela de *usage* (PodMetrics) — nunca confundir com request/limit."""
    rows: list[tuple[str, ...]] = []
    for wl in workloads:
        for snapshot in wl.metrics:
            for cm in snapshot.containers:
                ts = snapshot.timestamp or "—"
                rows.append(
                    (
                        f"`{snapshot.pod_name}`",
                        f"`{wl.name}`",
                        f"`{cm.container_name}`",
                        _format_usage_cpu(cm.cpu_usage),
                        _format_usage_memory(cm.memory_usage),
                        ts,
                    )
                )
    if not rows:
        return (
            "Métricas de runtime (CPU/memory **usage**) não disponíveis nos "
            "dados coletados.\n"
        )
    intro = (
        "> Valores abaixo são **uso real medido** (fonte: `pods.metrics.k8s.io`), "
        "snapshot pontual — **não** são requests nem limits configurados.\n\n"
    )
    return intro + _md_table(
        ("Pod", "Workload", "Container", "CPU usage", "Mem usage", "Timestamp"),
        rows,
    )


def _architecture_legend_kubediagrams() -> str:
    return (
        "**Diagrama gerado com [KubeDiagrams](https://github.com/philippemerle/KubeDiagrams)** "
        "a partir dos manifests YAML do namespace.\n\n"
        "- **Ícones** — recursos Kubernetes/OpenShift padrão (Deployment, Service, Route, etc.).\n"
        "- **Agrupamentos** — namespace e labels de aplicação (`app`, `app.kubernetes.io/name`).\n"
        "- **Arestas** — relações declaradas nos YAMLs (owner, selector, reference).\n\n"
        "> O diagrama reflete o inventário coletado, não o estado em tempo real do cluster.\n"
    )


def _architecture_legend_custom() -> str:
    return (
        "**Legenda dos grupos:**\n\n"
        "- **Namespace atual** — Pods (workloads), Services e Routes do namespace.\n"
        "- **Outros namespaces** — dependências com namespace explícito nos YAMLs.\n"
        "- **Fora do cluster** — clientes HTTP(S), bancos de dados e destinos "
        "`ExternalName` evidenciados nos YAMLs.\n\n"
        "**Tipos de aresta:** rótulos indicam a relação comprovada (ex.: `selector`, "
        "`spec.to`, `credenciais DB`, `env`) e o escopo (`interno`, "
        "`entre namespaces`, `externo`).\n\n"
        "> Contagem de instâncias nos Pods: réplicas desejadas/prontas do Deployment "
        "(ou pods coletados no inventário, quando aplicável).\n\n"
        "> O diagrama foca em fluxos de comunicação. Secrets, imagens de container "
        "e ConfigMaps não são exibidos — apenas relações evidenciadas no inventário YAML.\n"
    )


def _namespace_architecture_section(
    bundle: AssessmentBundle,
    diagram_renderer: DiagramRenderer | None,
) -> str:
    """Diagrama de arquitetura do namespace (somente KubeDiagrams)."""
    diagram = build_namespace_architecture_diagram(bundle)
    manifests = manifests_for_namespace_architecture(bundle)

    if not manifests and diagram is None:
        return (
            "> Não foram identificadas relações de comunicação suficientes no "
            "inventário YAML para representar a arquitetura deste namespace.\n"
        )

    image_path: str | None = None
    used_kubediagrams = False
    yaml_sources: tuple[str, ...] = ()

    if diagram_renderer is not None:
        result = diagram_renderer.render_flowchart(
            "namespace_architecture",
            manifests,
            diagram,
        )
        image_path = result.image_relpath
        used_kubediagrams = result.engine == "kubediagrams"
        yaml_sources = result.yaml_sources

    if image_path is None or not used_kubediagrams:
        return (
            "> Diagrama de arquitetura indisponível: KubeDiagrams não instalado "
            "ou falha na renderização.\n"
        )

    legend = _architecture_legend_kubediagrams()
    lines = [legend, ""]
    if yaml_sources:
        lines.append("**Manifests YAML utilizados:**")
        for source in yaml_sources[:12]:
            lines.append(f"- `{source}`")
        if len(yaml_sources) > 12:
            lines.append(f"- _… e mais {len(yaml_sources) - 12} arquivo(s)_")
        lines.append("")
    lines.append(_markdown_image("Arquitetura do namespace", image_path))
    lines.append("")
    return "\n".join(lines)


def _namespace_totals_table(bundle: AssessmentBundle) -> str:
    wl_diag = bundle.diagnostic.workloads
    wn_diag = bundle.diagnostic.worknodes
    workloads = bundle.context.workloads
    nodes = bundle.context.nodes

    _, pool_nodes, pool_desc = _pool_summary(nodes, workloads)
    pool_cpu = pool_cpu_allocatable_millicores(pool_nodes)
    pool_mem = pool_memory_allocatable_bytes(pool_nodes)

    pool_cpu_display = (
        format_cpu_millicores(pool_cpu) if pool_cpu is not None else "indisponível"
    )
    pool_mem_display = (
        format_memory_bytes(pool_mem) if pool_mem is not None else "indisponível"
    )

    rows = [
        (
            "CPU request (soma namespace)",
            wl_diag.cpu_requests.display,
            wl_diag.cpu_requests.note or "—",
        ),
        (
            "CPU limit (soma namespace)",
            wl_diag.cpu_limits.display,
            wl_diag.cpu_limits.note or "—",
        ),
        (
            "Memória request (soma namespace)",
            wl_diag.memory_requests.display,
            wl_diag.memory_requests.note or "—",
        ),
        (
            "Memória limit (soma namespace)",
            wl_diag.memory_limits.display,
            wl_diag.memory_limits.note or "—",
        ),
        (
            "Nós worker (coletados)",
            str(wn_diag.worknode_count),
            "Total no dump de worknodes",
        ),
        (
            "Pool de scheduling relevante",
            f"{len(pool_nodes)} nó(s)",
            f"`{pool_desc}`",
        ),
        (
            "CPU allocatable (pool relevante)",
            pool_cpu_display,
            "—",
        ),
        (
            "Memória allocatable (pool relevante)",
            pool_mem_display,
            "—",
        ),
    ]
    return _md_table(("Métrica", "Valor", "Observação"), list(rows))


def _resource_balance_table(bundle: AssessmentBundle) -> str:
    """Comparativo request/limit/usage agregado do namespace (snapshot)."""
    wl_diag = bundle.diagnostic.workloads
    workloads = bundle.context.workloads

    cpu_usage, mem_usage = aggregate_runtime_usage(workloads)

    def _pct(usage: float | None, total_norm: float | None) -> str:
        if usage is None or total_norm is None or total_norm <= 0:
            return "—"
        return f"{usage / total_norm * 100:.1f}%"

    cpu_req = wl_diag.cpu_requests.total_normalized
    cpu_lim = wl_diag.cpu_limits.total_normalized
    mem_req = wl_diag.memory_requests.total_normalized
    mem_lim = wl_diag.memory_limits.total_normalized

    rows = [
        (
            "CPU",
            wl_diag.cpu_requests.display,
            wl_diag.cpu_limits.display,
            format_cpu_millicores(cpu_usage) if cpu_usage is not None else "indisponível",
            _pct(cpu_usage, cpu_req),
            _pct(cpu_usage, cpu_lim),
        ),
        (
            "Memória",
            wl_diag.memory_requests.display,
            wl_diag.memory_limits.display,
            format_memory_bytes(mem_usage) if mem_usage is not None else "indisponível",
            _pct(mem_usage, mem_req),
            _pct(mem_usage, mem_lim),
        ),
    ]
    intro = (
        "> Uso real é **snapshot pontual** (PodMetrics); requests/limits são "
        "configuração declarada nos controllers de workload.\n\n"
    )
    return intro + _md_table(
        (
            "Recurso",
            "Total request",
            "Total limit",
            "Uso real (snapshot)",
            "Uso vs request",
            "Uso vs limit",
        ),
        rows,
    )


def _workload_kinds_summary(workloads: tuple[Workload, ...]) -> str:
    counts: dict[str, int] = {}
    for wl in workloads:
        counts[wl.kind] = counts.get(wl.kind, 0) + 1
    if not counts:
        return "_Nenhum workload identificado._\n"
    rows = [(kind, str(count)) for kind, count in sorted(counts.items())]
    return _md_table(("Controller", "Quantidade"), rows)


def _workloads_summary_table(workloads: tuple[Workload, ...]) -> str:
    rows: list[tuple[str, ...]] = []
    for wl in workloads:
        replicas = _replicas_display(wl)
        rows.append((f"`{wl.name}`", wl.kind, replicas, wl.qos_class or "—"))
    return _md_table(
        ("Workload", "Kind", "Réplicas (desej./prontas)", "QoS"),
        rows,
    )


def _findings_index_table(
    findings: tuple[Finding, ...],
    section_ids: dict[str, str],
) -> str:
    rows: list[tuple[str, ...]] = []
    for group in group_identical_res_findings(findings):
        primary = group[0]
        summary = primary.analysis
        if len(summary) > 120:
            summary = summary[:117] + "..."
        if len(group) == 1:
            finding_id = _finding_link(primary.id, section_ids)
            workload_col = primary.workload or "—"
        else:
            first_id = group[0].id
            last_id = group[-1].id
            finding_id = (
                f"{_finding_link(first_id, section_ids)} … "
                f"{_finding_link(last_id, section_ids)} "
                f"({len(group)})"
            )
            workload_col = f"{len(group)} workloads"
        rows.append(
            (
                finding_id,
                primary.severity.value,
                primary.category,
                workload_col,
                summary.replace("|", "\\|"),
            )
        )
    return _md_table(
        ("ID", "Severidade", "Categoria", "Workload", "Resumo"),
        rows,
    )


def _severity_priority(severity: Severity) -> str:
    if severity in (Severity.CRITICAL, Severity.HIGH):
        return "Alta"
    if severity == Severity.MEDIUM:
        return "Média"
    return "Baixa"


def _acceptance_criterion(finding: Finding) -> str:
    category = finding.category
    if category in ("MEM",):
        return "Uso de memória confortavelmente abaixo do novo request em métricas de 7 dias"
    if category in ("PROBE",):
        return "Probes respondem OK em ambiente saudável; pod reinicia em falha simulada"
    if category in ("CPU", "RES"):
        return "Validar com métricas históricas de 7–30 dias antes de promover a produção"
    if category in ("SCHED", "WNODE", "REPLICA"):
        return "Réplicas distribuídas em nós distintos (`oc get pods -o wide`)"
    if category in _ML_CATEGORIES:
        return "Investigação documentada; sem ação obrigatória sem evidência adicional"
    return "Validar em ambiente não produtivo antes de promover"


def _action_plan_table(
    findings: tuple[Finding, ...],
    section_ids: dict[str, str],
) -> str:
    actionable = [f for f in findings if f.recommendation]
    if not actionable:
        return "_Nenhuma ação recomendada com os dados atuais._\n"

    # Ordenar por prioridade
    order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFO: 4}
    actionable.sort(key=lambda f: (order.get(f.severity, 5), f.id))

    rows: list[tuple[str, ...]] = []
    seen: set[str] = set()
    for finding in actionable:
        key = finding.recommendation or ""
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            (
                _severity_priority(finding.severity),
                finding.recommendation or "—",
                _finding_link(finding.id, section_ids),
                _acceptance_criterion(finding),
            )
        )
    return _md_table(
        ("Prioridade", "Ação", "Finding", "Critério de aceite"),
        rows,
    )


def _findings_by_categories(
    findings: tuple[Finding, ...],
    categories: tuple[str, ...],
) -> tuple[Finding, ...]:
    cat_set = set(categories)
    return tuple(f for f in findings if f.category in cat_set)


def _finding_anchor_id(finding_id: str) -> str:
    return finding_id.lower()


def _finding_link(finding_id: str, section_ids: dict[str, str]) -> str:
    section_id = section_ids.get(finding_id, finding_id)
    anchor = _finding_anchor_id(section_id)
    return f"[`{finding_id}`](#{anchor})"


def _format_finding_with_anchor(findings: tuple[Finding, ...]) -> str:
    """Renderiza um finding isolado ou um grupo RES-* equivalente."""
    return format_grouped_finding(findings)


def _section_findings(findings: tuple[Finding, ...], intro: str) -> str:
    if not findings:
        return f"{intro}\n\n_Nenhum finding nesta categoria._\n"
    parts = [intro, ""]
    for group in group_identical_res_findings(findings):
        parts.append(_format_finding_with_anchor(group))
        parts.append("")
    return "\n".join(parts)


def _executive_narrative(
    report: AnalysisReport,
    bundle: AssessmentBundle,
) -> list[str]:
    """Sumário executivo narrativo — temas transversais, não lista de IDs."""
    lines: list[str] = []
    workloads = bundle.context.workloads
    by_sev = {s: report.by_severity(s) for s in Severity}

    lines.append(
        f"O namespace `{report.namespace}` foi analisado com **{report.workloads_analyzed} "
        f"workload(s)** e **{report.worknodes_considered} nó(s) worker** no dump coletado. "
        f"Foram registrados **{report.finding_count} findings** "
        f"({len(by_sev[Severity.CRITICAL])} CRITICAL, "
        f"{len(by_sev[Severity.HIGH])} HIGH, "
        f"{len(by_sev[Severity.MEDIUM])} MEDIUM)."
    )

    lines.append("\n**Principais achados:**\n")

    themes: list[str] = []

    cpu_usage, mem_usage = aggregate_runtime_usage(workloads)
    wl_diag = bundle.diagnostic.workloads
    cpu_req = wl_diag.cpu_requests.total_normalized
    mem_req = wl_diag.memory_requests.total_normalized

    if cpu_usage is not None and cpu_req and cpu_req > 0:
        pct = cpu_usage / cpu_req * 100
        if pct < 10:
            themes.append(
                f"1. **Superprovisionamento de CPU**: uso real agregado (~"
                f"{format_cpu_millicores(cpu_usage)}) representa ~{pct:.1f}% do "
                f"request total ({wl_diag.cpu_requests.display}) — folga significativa "
                "para redução de CPU request após validação histórica."
            )

    mem_high = [
        f for f in report.findings
        if f.category == "MEM" and f.severity in (Severity.HIGH, Severity.CRITICAL)
    ]
    if mem_high:
        themes.append(
            f"2. **Subprovisionamento de memória**: {len(mem_high)} pod(s) com uso "
            "de memória acima do request configurado no snapshot — risco elevado de "
            "eviction em pressão de memória (classe Burstable)."
        )
    elif mem_usage is not None and mem_req and mem_usage > mem_req:
        themes.append(
            f"2. **Memória**: uso agregado ({format_memory_bytes(mem_usage)}) excede "
            f"request total ({wl_diag.memory_requests.display}) no snapshot coletado."
        )

    probe_high = [f for f in report.findings if f.category == "PROBE" and f.severity == Severity.HIGH]
    if probe_high:
        themes.append(
            f"3. **Probes ausentes**: {len(probe_high)} container(s) sem readinessProbe — "
            "Services podem encaminhar tráfego a pods não prontos."
        )

    sched_medium = [
        f for f in report.findings
        if f.category in ("SCHED", "REPLICA", "WNODE")
        and f.severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
    ]
    if sched_medium:
        themes.append(
            "4. **Scheduling e resiliência**: concentração de réplicas ou placement "
            "fora do pool esperado — avaliar nodeSelector, podAntiAffinity e "
            "topologySpreadConstraints."
        )

    route_findings = [f for f in report.findings if f.category == "ROUTE"]
    if route_findings:
        themes.append(
            f"5. **Exposição HTTP/TLS**: {len(route_findings)} Route(s) com "
            "`insecureEdgeTerminationPolicy: Allow` — tráfego HTTP não é "
            "redirecionado automaticamente para HTTPS."
        )

    log_findings = [f for f in report.findings if f.category == "LOG"]
    if log_findings:
        themes.append(
            f"6. **Observabilidade (logs)**: {len(log_findings)} achado(s) em logs "
            "coletados — nível DEBUG dominante ou arquivos vazios."
        )

    if report.ml_enabled:
        ml_count = sum(1 for f in report.findings if f.category in _ML_CATEGORIES)
        if ml_count:
            themes.append(
                f"7. **Sinais ML locais**: {ml_count} indício(s) estatístico(s) "
                "complementar(es) — interpretar como hipóteses para investigação, "
                "não como defeitos confirmados."
            )

    if not themes:
        themes.append(
            "1. Nenhum tema crítico consolidado — revisar findings nas seções "
            "analíticas para detalhes."
        )

    lines.extend(themes)
    return lines


def _derive_conclusion_priorities(findings: tuple[Finding, ...]) -> str:
    """Monta prioridades a partir dos findings do namespace — sem texto fixo."""
    topics: list[str] = []

    if any(
        f.category == "MEM" and f.severity in (Severity.HIGH, Severity.CRITICAL)
        for f in findings
    ):
        topics.append("ajuste de memory request")
    if any(
        f.category == "PROBE" and f.severity in (Severity.HIGH, Severity.CRITICAL)
        for f in findings
    ):
        topics.append("probes de saúde")
    if any(
        f.category in ("SCHED", "REPLICA", "WNODE")
        and f.severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
        for f in findings
    ):
        topics.append("distribuição de réplicas e scheduling")
    if any(
        f.category == "ROUTE"
        and f.severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
        for f in findings
    ):
        topics.append("hardening de Routes/TLS")
    if any(f.category == "CPU" for f in findings) and not any(
        f.category == "MEM" and f.severity in (Severity.HIGH, Severity.CRITICAL)
        for f in findings
    ):
        topics.append("otimização de CPU request")

    if topics:
        return "Priorizar " + ", ".join(topics) + ". "
    return "Revisar findings detalhados nas seções analíticas para próximos passos. "


def _conclusion_text(report: AnalysisReport, bundle: AssessmentBundle) -> str:
    high = len(report.by_severity(Severity.HIGH))
    critical = len(report.by_severity(Severity.CRITICAL))
    mem_high = sum(
        1 for f in report.findings
        if f.category == "MEM" and f.severity in (Severity.HIGH, Severity.CRITICAL)
    )
    cpu_findings = [f for f in report.findings if f.category == "CPU"]

    parts = [
        f"O namespace `{report.namespace}` apresenta **{report.workloads_analyzed} "
        f"workload(s)** analisado(s). ",
    ]

    if cpu_findings and mem_high:
        parts.append(
            "O snapshot indica CPU com reserva provavelmente acima do necessário "
            "em um ou mais workloads, enquanto memória pode estar abaixo do uso "
            "real observado. "
        )
    elif mem_high:
        parts.append("Há indícios de memória subdimensionada em relação ao uso medido. ")
    elif cpu_findings:
        parts.append(
            "Há oportunidades de revisão de CPU request com base no uso medido. "
        )
    else:
        parts.append("Revisar findings de recursos para ajustes pontuais. ")

    parts.append(
        f"Foram registrados {critical} finding(s) CRITICAL e {high} HIGH. "
    )
    parts.append(_derive_conclusion_priorities(report.findings))
    parts.append(
        "Validação com séries históricas de 7–30 dias é recomendada antes de "
        "alterações em produção."
    )
    return "".join(parts)


def _recommendations_list(
    findings: tuple[Finding, ...],
    section_ids: dict[str, str],
) -> str:
    recs: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        if not finding.recommendation:
            continue
        key = finding.recommendation.strip()
        if key in seen:
            continue
        seen.add(key)
        recs.append(f"- {key} ({_finding_link(finding.id, section_ids)})")
    if not recs:
        return "_Nenhuma recomendação específica gerada._\n"
    return "\n".join(recs) + "\n"


def _risks_list(
    findings: tuple[Finding, ...],
    section_ids: dict[str, str],
) -> str:
    risky = [
        f
        for f in findings
        if f.severity in (Severity.CRITICAL, Severity.HIGH)
    ]
    if not risky:
        return "_Nenhum risco classificado como HIGH ou CRITICAL._\n"
    lines: list[str] = []
    for finding in risky:
        impact = finding.impact or "Impacto não detalhado no finding."
        lines.append(
            f"- {_finding_link(finding.id, section_ids)} [{finding.severity.value}] — "
            f"{finding.analysis} *Impacto:* {impact}"
        )
    return "\n".join(lines) + "\n"


def _opportunities_list(
    findings: tuple[Finding, ...],
    section_ids: dict[str, str],
) -> str:
    opps = [
        f
        for f in findings
        if f.severity in (Severity.MEDIUM, Severity.LOW, Severity.INFO)
        and f.recommendation
        and f.category not in _ML_CATEGORIES
    ]
    if not opps:
        return "_Nenhuma oportunidade de otimização identificada com os dados atuais._\n"
    lines: list[str] = []
    seen: set[str] = set()
    for finding in opps[:15]:
        key = finding.recommendation or ""
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"- {finding.recommendation} ({_finding_link(finding.id, section_ids)})"
        )
    return "\n".join(lines) + "\n"


def _services_table(services: tuple[ServiceSpec, ...]) -> str:
    rows: list[tuple[str, ...]] = []
    for svc in services:
        port_parts: list[str] = []
        for p in svc.ports:
            tgt = p.target_port if p.target_port is not None else "—"
            port_parts.append(f"{p.port}→{tgt}")
        selector = ", ".join(f"{k}={v}" for k, v in sorted(svc.selector.items())) or "—"
        rows.append(
            (
                f"`{svc.name}`",
                svc.service_type or "—",
                svc.cluster_ip or "—",
                ", ".join(port_parts) if port_parts else "—",
                selector,
            )
        )
    return _md_table(
        ("Service", "Tipo", "ClusterIP", "Porta → TargetPort", "Seletor"),
        rows,
    )


def _routes_table(routes: tuple[RouteSpec, ...]) -> str:
    rows: list[tuple[str, ...]] = []
    for route in routes:
        rows.append(
            (
                f"`{route.name}`",
                route.host or "—",
                route.target_service or "—",
                str(route.target_port or "—"),
                route.tls_termination or "—",
                route.tls_insecure_policy or "—",
            )
        )
    return _md_table(
        ("Route", "Host", "Serviço destino", "Porta", "Termination", "Política insegura"),
        rows,
    )


def _configmaps_table(
    configmaps: tuple[ConfigMapSpec, ...],
    referenced: set[str],
) -> str:
    rows: list[tuple[str, ...]] = []
    for cm in configmaps:
        consumed = "Sim" if cm.name in referenced else "Não"
        keys = ", ".join(cm.keys) if cm.keys else "—"
        rows.append((f"`{cm.name}`", keys, consumed, cm.app_group or "—"))
    return _md_table(
        ("ConfigMap", "Chaves", "Consumido por workload?", "App group"),
        rows,
    )


def _secrets_table(refs: tuple[SecretReference, ...]) -> str:
    if not refs:
        return "_Nenhuma referência a Secret encontrada nos workloads analisados._\n"
    rows: list[tuple[str, ...]] = []
    for ref in refs:
        rows.append((f"`{ref.name}`", ref.usage, f"`{ref.workload}`"))
    intro = (
        "> Nenhum conteúdo de Secret foi lido ou reproduzido — apenas nomes e forma de uso.\n\n"
    )
    return intro + _md_table(("Secret (nome)", "Forma de uso", "Workload"), rows)


def _operators_table(operators: tuple[OperatorCSVSpec, ...]) -> str:
    if not operators:
        return "_Nenhum ClusterServiceVersion encontrado no dump._\n"
    rows: list[tuple[str, ...]] = []
    for op in operators:
        rows.append(
            (
                op.display_name or op.name,
                op.name,
                op.version or "—",
                op.phase or "—",
                op.reason or "—",
                op.upgrade_status or "—",
            )
        )
    note = (
        "> CSVs em phase `Succeeded` com reason `Copied` são operadores cluster-wide "
        "copiados para o namespace.\n\n"
    )
    return note + _md_table(
        ("Operador", "CSV", "Versão", "Phase", "Reason", "Upgrade"),
        rows,
    )


def _pod_logs_table(logs: tuple[PodLogSummary, ...]) -> str:
    if not logs:
        return "_Nenhum log de pod coletado._\n"
    rows: list[tuple[str, ...]] = []
    for log in logs:
        levels = ", ".join(f"{k}:{v}" for k, v in sorted(log.levels.items())) or "—"
        rows.append(
            (
                f"`{log.app_group}`",
                f"`{log.pod_name}`",
                str(log.line_count),
                "Sim" if log.empty else "Não",
                levels,
            )
        )
    return _md_table(
        ("App", "Pod", "Linhas", "Vazio?", "Níveis detectados"),
        rows,
    )


def _referenced_configmap_names(workloads: tuple[Workload, ...]) -> set[str]:
    refs: set[str] = set()
    for wl in workloads:
        refs.update(wl.referenced_configmaps)
    return refs


def _acronyms_legend() -> str:
    parts = [
        "Glossário das siglas e abreviações utilizadas neste relatório.\n",
        "### Categorias de findings\n",
        _md_table(("Sigla", "Descrição"), list(_FINDING_CATEGORY_LEGEND)),
        "### Níveis de severidade\n",
        _md_table(("Sigla", "Descrição"), list(_SEVERITY_LEGEND)),
        "### Níveis de confiança\n",
        _md_table(("Sigla", "Descrição"), list(_CONFIDENCE_LEGEND)),
        "### Termos técnicos\n",
        _md_table(("Sigla", "Descrição"), list(_TECHNICAL_ACRONYMS)),
    ]
    return "\n".join(parts)


def _references_section() -> str:
    redhat_tech_rows = [
        (topic, f"[{title}]({url})")
        for topic, title, url in _REDHAT_TECHNICAL_DOCUMENTATION
    ]
    supplementary_tech_rows = [
        (topic, f"[{title}]({url})")
        for topic, title, url in _SUPPLEMENTARY_TECHNICAL_DOCUMENTATION
    ]
    parts = [
        "Fontes consultadas para fundamentar metodologia, terminologia e "
        "recomendações deste relatório. **Prioridade:** documentação e "
        "publicações Red Hat; referências upstream complementam quando "
        "não há equivalente específico em OpenShift.\n",
        "### Documentação técnica — Red Hat\n",
        _md_table(("Tema", "Referência"), redhat_tech_rows),
        "### Documentação técnica complementar (upstream)\n",
        _md_table(("Tema", "Referência"), supplementary_tech_rows),
        "### Referências bibliográficas — Red Hat\n",
        _md_table(("Referência", "Relevância"), list(_REDHAT_BIBLIOGRAPHIC_REFERENCES)),
        "### Referências bibliográficas complementares\n",
        _md_table(
            ("Referência", "Relevância"),
            list(_SUPPLEMENTARY_BIBLIOGRAPHIC_REFERENCES),
        ),
    ]
    return "\n".join(parts)


def _build_report_frontmatter(namespace: str) -> str:
    """Metadados YAML para conversores (Pandoc, etc.) reconhecerem pt-BR e UTF-8."""
    title = f"Relatório de Assessment — Namespace {namespace}"
    return (
        "---\n"
        f"title: \"{title}\"\n"
        f"lang: {REPORT_FILE_LANGUAGE}\n"
        "babel-lang: brazil\n"
        "dir: ltr\n"
        "---\n"
    )


def _prepare_report_content(content: str) -> str:
    """Normaliza quebras de linha e garante texto Unicode válido para UTF-8."""
    return content.replace("\r\n", "\n").replace("\r", "\n")


class MarkdownReportGenerator:
    """Monta relatório Markdown completo a partir de um ``AssessmentBundle``."""

    def generate(
        self,
        bundle: AssessmentBundle,
        *,
        assets_dir: Path | None = None,
    ) -> str:
        report = bundle.analysis
        ctx = bundle.context
        diag = bundle.diagnostic
        section_ids = finding_section_ids(report.findings)
        assets_prefix = report_assets_prefix(report.namespace)
        renderers = (
            create_renderers(bundle, assets_dir, assets_prefix=assets_prefix)
            if assets_dir is not None
            else None
        )
        visualizations = VisualizationPipeline().build(
            bundle,
            renderers=renderers,
        )
        ns = report.namespace
        generated = bundle.generated_at.strftime("%d/%m/%Y %H:%M UTC")

        sections: list[str] = [
            _build_report_frontmatter(ns),
            f"# Relatório de Assessment — Namespace `{ns}`",
            "",
            f"**Namespace analisado:** `{ns}`",
            f"**Fonte dos dados:** `{bundle.config.workloads_base / ns}`",
            f"**Worknodes:** `{bundle.config.worknodes_path}`",
            f"**Data de geração:** {generated}",
            f"**Gerado por:** kubeoptix-core-ai",
            "",
            "> Este relatório foi produzido exclusivamente a partir dos artefatos "
            "YAML ingeridos pelo agente. Nenhum dado foi inventado; onde a evidência "
            "é insuficiente, isso é indicado explicitamente. **Request/limit** "
            "referem-se a configuração declarada; **usage** refere-se a métricas de "
            "runtime (PodMetrics), quando disponíveis.",
            "",
            "---",
            "",
            "## 1. Legenda de siglas",
            "",
        ]
        sections.append(_acronyms_legend())

        sections.extend(["", "---", "", "## 2. Sumário executivo", ""])

        for line in _executive_narrative(report, bundle):
            sections.append(line)
        sections.append("")
        sections.append(_workloads_summary_table(ctx.workloads))

        sections.extend(["", "---", "", "## 3. Escopo da análise", ""])
        sections.append(
            f"- **Workloads analisados:** {report.workloads_analyzed}\n"
            f"- **Worknodes considerados:** {report.worknodes_considered}\n"
            f"- **Arquivos encontrados:** {diag.files_found_count}\n"
            f"- **Arquivos processados:** {diag.files_processed_count}\n"
            f"- **Arquivos ignorados:** {diag.files_ignored_count}\n"
            f"- **Erros de parsing:** {len(diag.parse_errors)}\n"
            f"- **Camada ML local:** {'ativada' if report.ml_enabled else 'desativada'}"
        )
        sections.extend(["", "---", "", "## 4. Fontes de dados", ""])
        sections.append(
            "Tipos de artefato considerados nesta execução:\n\n"
            "- Workloads: Deployment, StatefulSet, DaemonSet, DeploymentConfig, "
            "Job, CronJob, ReplicationController (`apps/{app}/` e `resources/`)\n"
            "- Pods (`apps/*/pods/`, `resources/pods/`)\n"
            "- Autoscaling: HPA, VPA (`apps/*/hpa|vpa/` ou `resources/`)\n"
            "- PDB (`apps/*/pdb/` ou `resources/poddisruptionbudgets.policy/`)\n"
            "- PodMetrics (`apps/*/pods.metrics.k8s.io/`, `resources/pods.metrics.k8s.io/`)\n"
            "- PVCs (`apps/*/persistentvolumeclaims/`, `resources/persistentvolumeclaims/`)\n"
            "- Services (`resources/services/`, `apps/*/services/`)\n"
            "- Routes (`resources/routes.route.openshift.io/`, `apps/*/routes/`)\n"
            "- ConfigMaps (`resources/configmaps/`, `apps/*/configmaps/`)\n"
            "- Secrets (referências por nome nos workloads)\n"
            "- ClusterServiceVersions / PackageManifests (OLM)\n"
            "- Logs de pods (`apps/*/pod-logs/*.log`)\n"
            "- Worknodes (`worknodes/*.yaml`)\n\n"
            "**Correlação:** pods são associados ao controller canônico via "
            "ownerReferences (Pod → ReplicaSet → Deployment, Pod → StatefulSet, "
            "Job → CronJob, etc.). A pasta `apps/{app_group}/` é varrida "
            "recursivamente e fundida com `resources/`. ReplicaSets históricos "
            "não geram workloads duplicados.\n\n"
            "**Não analisados nesta versão:** conteúdo de Secrets (apenas referências "
            "por nome), eventos, NetworkPolicies, séries temporais."
        )
        if diag.processed_files:
            sections.append("\nArquivos processados (amostra):\n")
            base = bundle.config.workloads_base
            for path in diag.processed_files[:20]:
                sections.append(f"- `{_relative_path(path, base)}`")
            if len(diag.processed_files) > 20:
                sections.append(f"- _… e mais {len(diag.processed_files) - 20} arquivo(s)_")

        sections.extend(["", "---", "", "## 5. Visão geral do namespace", ""])
        sections.append(_namespace_totals_table(bundle))
        sections.append("\n### Comparativo request / limit / uso (snapshot)\n")
        sections.append(_resource_balance_table(bundle))
        sections.append("\n### Arquitetura\n")
        sections.append(
            _namespace_architecture_section(
                bundle,
                renderers.diagram if renderers is not None else None,
            )
        )
        sections.append("\n### Visualizações\n")
        sections.append(render_section_visualizations(visualizations.by_section("namespace_overview")))

        sections.extend(["", "---", "", "## 6. Workloads identificados", ""])

        if ctx.services:
            sections.append("### Inventário — Services\n")
            sections.append(_services_table(ctx.services))
        if ctx.routes:
            sections.append("\n### Inventário — Routes (exposição externa)\n")
            sections.append(_routes_table(ctx.routes))
        if ctx.configmaps:
            sections.append("\n### Inventário — ConfigMaps\n")
            sections.append(
                _configmaps_table(ctx.configmaps, _referenced_configmap_names(ctx.workloads))
            )
        sections.append("\n### Inventário — Secrets referenciados\n")
        sections.append(_secrets_table(ctx.secret_references))
        if ctx.operators:
            sections.append("\n### Inventário — Operadores (ClusterServiceVersions)\n")
            sections.append(_operators_table(ctx.operators))
        if ctx.pod_logs:
            sections.append("\n### Inventário — Logs de pods (amostra)\n")
            sections.append(_pod_logs_table(ctx.pod_logs))

        inventory_findings = _findings_by_categories(
            report.findings, _SECTION_CATEGORIES["inventory"]
        )
        if inventory_findings:
            sections.append(
                _section_findings(inventory_findings, "Findings de inventário / observabilidade:")
            )

        sections.append("\n### Workloads consolidados (todos os controllers)\n")
        sections.append(_workload_kinds_summary(ctx.workloads))
        sections.append("\n### Detalhamento por workload\n")
        sections.append(_workloads_table(ctx.workloads))
        sections.append("\n### Placement observado\n")
        sections.append(_placement_table(ctx.workloads, ctx.nodes))

        sections.append("\n### Comunicação\n")
        sections.append("#### 1. Externa → OpenShift\n")
        sections.append(
            render_section_visualizations(visualizations.by_section("communication_external"))
        )
        sections.append("#### 2. Comunicação interna\n")
        sections.append(
            render_section_visualizations(visualizations.by_section("communication_internal"))
        )
        sections.append("#### 3. Dependências externas\n")
        sections.append(
            render_section_visualizations(
                visualizations.by_section("communication_dependencies")
            )
        )

        sections.append("\n### Visualizações\n")
        sections.append(render_section_visualizations(visualizations.by_section("workloads")))

        sections.extend(["", "---", "", "## 7. Análise de CPU", ""])
        sections.append("### Configuração (request/limit)\n")
        sections.append(
            "Valores de **request** e **limit** abaixo são configurados nos "
            "controllers de workload — não representam uso real.\n"
        )
        cpu_rows: list[tuple[str, ...]] = []
        for wl in ctx.workloads:
            cpu_rows.append(
                (
                    f"`{wl.name}`",
                    _container_cpu_request_m(wl),
                    _container_cpu_limit_m(wl),
                    str(wl.replicas_desired or "—"),
                )
            )
        sections.append(
            _md_table(
                ("Workload", "CPU request/pod", "CPU limit/pod", "Réplicas"),
                cpu_rows,
            )
        )
        sections.append("\n### Uso real (PodMetrics)\n")
        sections.append(_runtime_metrics_table(ctx.workloads))
        sections.append("\n### Visualizações\n")
        sections.append(render_section_visualizations(visualizations.by_section("cpu")))
        sections.append(
            _section_findings(
                _findings_by_categories(report.findings, _SECTION_CATEGORIES["cpu"]),
                "Findings de CPU e recursos relacionados:",
            )
        )

        sections.extend(["", "---", "", "## 8. Análise de memória", ""])
        mem_rows: list[tuple[str, ...]] = []
        for wl in ctx.workloads:
            mem_rows.append(
                (
                    f"`{wl.name}`",
                    _container_mem_request(wl),
                    _container_mem_limit(wl),
                    str(wl.replicas_desired or "—"),
                )
            )
        sections.append(
            _md_table(
                ("Workload", "Mem request/pod", "Mem limit/pod", "Réplicas"),
                mem_rows,
            )
        )
        sections.append("\n### Visualizações\n")
        sections.append(render_section_visualizations(visualizations.by_section("memory")))
        sections.append(
            _section_findings(
                _findings_by_categories(report.findings, _SECTION_CATEGORIES["memory"]),
                "Findings de memória:",
            )
        )

        for title, key in (
            ("## 9. Análise de QoS", "qos"),
            ("## 10. Análise de réplicas", "replicas"),
            ("## 11. Análise de probes", "probes"),
            ("## 12. Análise de scheduling", "scheduling"),
            ("## 13. Análise de storage", "storage"),
        ):
            sections.extend(["", "---", "", title, ""])
            if key == "qos":
                sections.append("\n### Visualizações\n")
                sections.append(render_section_visualizations(visualizations.by_section("qos")))
            sections.append(
                _section_findings(
                    _findings_by_categories(report.findings, _SECTION_CATEGORIES[key]),
                    f"Findings da categoria {key}:",
                )
            )

        sections.extend(["", "---", "", "## 14. Correlação workload × worknode", ""])
        sections.append(_placement_table(ctx.workloads, ctx.nodes))
        sections.append("\n### Visualizações\n")
        sections.append(render_section_visualizations(visualizations.by_section("workload_node")))
        sections.append(
            _section_findings(
                _findings_by_categories(
                    report.findings, _SECTION_CATEGORIES["workload_node"]
                ),
                "Findings de correlação workload × worknode:",
            )
        )

        sections.extend(["", "---", "", "## 15. Anomalias identificadas", ""])
        if report.ml_enabled:
            sections.append(
                "Sinais da camada estatística/ML local. Outlier estatístico "
                "**não implica** defeito operacional.\n"
            )
            sections.append(
                _section_findings(
                    _findings_by_categories(
                        report.findings, _SECTION_CATEGORIES["anomalies"]
                    ),
                    "Findings estatísticos / ML:",
                )
            )
        else:
            sections.append("_Camada ML local desativada nesta execução._\n")

        sections.extend(["", "---", "", "## 16. Findings", ""])
        grouped_count = len(group_identical_res_findings(report.findings))
        sections.append(
            f"Total: **{report.finding_count}** findings "
            f"({grouped_count} entradas após agrupar RES-* equivalentes). "
            "Detalhes completos nas seções analíticas (7–15); "
            "índice resumido abaixo.\n"
        )
        sections.append(_findings_index_table(report.findings, section_ids))
        sections.append("\n### Visualizações\n")
        sections.append(render_section_visualizations(visualizations.by_section("findings")))

        sections.extend(["", "---", "", "## 17. Oportunidades de otimização", ""])
        sections.append(_opportunities_list(report.findings, section_ids))

        sections.extend(["", "---", "", "## 18. Riscos", ""])
        sections.append(_risks_list(report.findings, section_ids))

        sections.extend(["", "---", "", "## 19. Recomendações", ""])
        sections.append("### Plano de ação\n")
        sections.append(_action_plan_table(report.findings, section_ids))
        sections.append("\n### Lista consolidada\n")
        sections.append(_recommendations_list(report.findings, section_ids))

        sections.extend(["", "---", "", "## 20. Conclusão", ""])
        sections.append(_conclusion_text(report, bundle))

        sections.extend(["", "---", "", "## 21. Limitações da análise", ""])
        if report.limitations:
            for lim in report.limitations:
                sections.append(f"- {lim}")
        else:
            sections.append("- Nenhuma limitação adicional registrada.")
        sections.append(
            "\n- Este relatório **não** inclui conteúdo de Secrets, eventos de "
            "OOMKilled, throttling de CPU ou séries temporais — salvo quando "
            "explicitamente presentes nos artefatos ingeridos."
        )

        sections.extend(["", "---", "", "## 22. Referências", ""])
        sections.append(_references_section())

        return _prepare_report_content("\n".join(sections) + "\n")


def write_assessment_report(
    bundle: AssessmentBundle,
    output_dir: Path,
    *,
    inline_images: bool = True,
) -> Path:
    """Gera `<namespace>.md` e pasta `<namespace>_assets/` no diretório de saída."""
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_prefix = report_assets_prefix(bundle.analysis.namespace)
    assets_dir = output_dir / assets_prefix
    path = output_dir / f"{bundle.analysis.namespace}.md"
    content = MarkdownReportGenerator().generate(bundle, assets_dir=assets_dir)
    if inline_images:
        content = embed_markdown_images(content, markdown_dir=output_dir)
    path.write_bytes(content.encode(REPORT_FILE_ENCODING))
    return path
