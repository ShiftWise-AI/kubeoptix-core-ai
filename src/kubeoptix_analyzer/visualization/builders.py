"""Builders que convertem datasets em VisualizationSpec."""

from __future__ import annotations

from kubeoptix_analyzer.report.pipeline import AssessmentBundle
from kubeoptix_analyzer.visualization.datasets import communication, composition, numeric, workload
from kubeoptix_analyzer.visualization.interpretation import interpret_visualization
from kubeoptix_analyzer.visualization.mermaid import MermaidGenerator
from kubeoptix_analyzer.visualization.models import (
    ChartDataset,
    CompositionDataset,
    FlowchartDataset,
    ProvenanceRef,
    VisualizationSpec,
    VisualizationStatus,
    VisualizationBundle,
)

_generator = MermaidGenerator()


def _collect_provenance_numeric(dataset: ChartDataset) -> tuple[ProvenanceRef, ...]:
    refs: list[ProvenanceRef] = []
    for series in dataset.series:
        for point in series.points:
            refs.extend(point.provenance)
    return tuple(refs)


def _collect_provenance_composition(dataset: CompositionDataset) -> tuple[ProvenanceRef, ...]:
    refs: list[ProvenanceRef] = []
    for slice_ in dataset.slices:
        refs.extend(slice_.provenance)
    return tuple(refs)


def _collect_provenance_flowchart(dataset: FlowchartDataset) -> tuple[ProvenanceRef, ...]:
    refs: list[ProvenanceRef] = []
    for node in dataset.nodes:
        refs.extend(node.provenance)
    for edge in dataset.edges:
        refs.extend(edge.evidence)
    return tuple(refs)


def _spec_from_numeric(
    viz_id: str,
    section: str,
    dataset: ChartDataset,
) -> VisualizationSpec:
    mermaid = _generator.render_numeric(dataset)
    provenance = _collect_provenance_numeric(dataset)
    interpretation = interpret_visualization(dataset)
    return VisualizationSpec(
        id=viz_id,
        title=dataset.title,
        question=dataset.question,
        section=section,
        status=VisualizationStatus.AVAILABLE,
        mermaid=mermaid,
        interpretation=interpretation,
        provenance=provenance,
        dataset_kind="numeric",
    )


def _spec_from_composition(
    viz_id: str,
    section: str,
    dataset: CompositionDataset,
) -> VisualizationSpec:
    mermaid = _generator.render_composition(dataset)
    provenance = _collect_provenance_composition(dataset)
    interpretation = interpret_visualization(dataset)
    return VisualizationSpec(
        id=viz_id,
        title=dataset.title,
        question=dataset.question,
        section=section,
        status=VisualizationStatus.AVAILABLE,
        mermaid=mermaid,
        interpretation=interpretation,
        provenance=provenance,
        dataset_kind="composition",
    )


def _spec_from_flowchart(
    viz_id: str,
    section: str,
    dataset: FlowchartDataset,
) -> VisualizationSpec:
    mermaid = _generator.render_flowchart(dataset)
    provenance = _collect_provenance_flowchart(dataset)
    interpretation = interpret_visualization(dataset)
    return VisualizationSpec(
        id=viz_id,
        title=dataset.title,
        question=dataset.question,
        section=section,
        status=VisualizationStatus.AVAILABLE,
        mermaid=mermaid,
        interpretation=interpretation,
        provenance=provenance,
        dataset_kind="flowchart",
    )


def _unavailable(
    viz_id: str,
    title: str,
    question: str,
    section: str,
    reason: str,
    *,
    dataset_kind: str = "numeric",
) -> VisualizationSpec:
    return VisualizationSpec(
        id=viz_id,
        title=title,
        question=question,
        section=section,
        status=VisualizationStatus.UNAVAILABLE,
        unavailable_reason=reason,
        interpretation=f"**Limitação:** {reason}",
        dataset_kind=dataset_kind,  # type: ignore[arg-type]
    )


def build_all_visualizations(bundle: AssessmentBundle) -> VisualizationBundle:
    specs: list[VisualizationSpec] = []

    # §4 — visão geral
    ns_chart = numeric.build_namespace_requests_vs_allocatable(bundle)
    if ns_chart:
        specs.append(_spec_from_numeric("ns_requests_allocatable", "namespace_overview", ns_chart))
    else:
        specs.append(
            _unavailable(
                "ns_requests_allocatable",
                "Requests do namespace × capacidade allocatable",
                "Os requests agregados cabem no pool de scheduling?",
                "namespace_overview",
                "Dados de request do namespace ou capacidade allocatable do pool indisponíveis.",
            )
        )

    qos_chart = composition.build_qos_distribution(bundle)
    if qos_chart:
        specs.append(_spec_from_composition("qos_distribution", "namespace_overview", qos_chart))

    # §5 — workloads
    workload_diagrams = workload.build_workload_diagrams(bundle)
    if workload_diagrams:
        for idx, diagram in enumerate(workload_diagrams):
            specs.append(
                _spec_from_flowchart(f"workload_diagram_{idx}", "workloads", diagram)
            )
    else:
        specs.append(
            _unavailable(
                "workload_diagram",
                "Diagrama de workloads",
                "Quais recursos cada workload utiliza?",
                "workloads",
                "Nenhum workload disponível para diagrama.",
                dataset_kind="flowchart",
            )
        )

    external_diagrams = communication.build_external_communication_diagrams(bundle)
    if external_diagrams:
        for diagram in external_diagrams:
            route_key = diagram.title.rsplit(" — ", 1)[-1]
            specs.append(
                _spec_from_flowchart(
                    f"ext_comm_{route_key}",
                    "communication_external",
                    diagram,
                )
            )
    else:
        specs.append(
            _unavailable(
                "external_communication",
                "Comunicação externa → OpenShift",
                "Como Routes expõem serviços para fora do cluster?",
                "communication_external",
                "Nenhuma Route encontrada nos dados coletados.",
                dataset_kind="flowchart",
            )
        )

    internal_diagrams = communication.build_internal_communication_diagrams(bundle)
    if internal_diagrams:
        for diagram in internal_diagrams:
            svc_key = diagram.title.rsplit(" — ", 1)[-1]
            specs.append(
                _spec_from_flowchart(
                    f"int_comm_{svc_key}",
                    "communication_internal",
                    diagram,
                )
            )
    else:
        specs.append(
            _unavailable(
                "internal_communication",
                "Comunicação interna",
                "Quais Services selecionam workloads?",
                "communication_internal",
                "Sem evidência de Service→Workload (selector compatível com labels do pod).",
                dataset_kind="flowchart",
            )
        )

    dependency_diagrams = communication.build_external_dependencies_diagrams(bundle)
    if dependency_diagrams:
        for diagram in dependency_diagrams:
            wl_key = diagram.title.rsplit(" — ", 1)[-1]
            specs.append(
                _spec_from_flowchart(
                    f"ext_dep_{wl_key}",
                    "communication_dependencies",
                    diagram,
                )
            )
    else:
        specs.append(
            _unavailable(
                "external_dependencies",
                "Dependências externas",
                "Quais sistemas externos os workloads utilizam?",
                "communication_dependencies",
                "Sem evidência de registry, Secret ou sinais de runtime em logs.",
                dataset_kind="flowchart",
            )
        )

    # §6 — CPU
    for builder, viz_id, title, question in (
        (numeric.build_cpu_request_chart, "cpu_request", "CPU request por workload", "Quanto CPU cada workload reserva?"),
        (numeric.build_cpu_limit_chart, "cpu_limit", "CPU limit por workload", "Qual o limit de CPU por pod?"),
        (numeric.build_cpu_request_limit_chart, "cpu_request_limit", "CPU request × limit", "Como request e limit se comparam?"),
    ):
        chart = builder(bundle)
        if chart:
            specs.append(_spec_from_numeric(viz_id, "cpu", chart))
        else:
            specs.append(
                _unavailable(viz_id, title, question, "cpu", "Valores de CPU não disponíveis nos Deployments.")
            )

    # §7 — memória
    for builder, viz_id, title, question in (
        (numeric.build_memory_request_chart, "mem_request", "Memória request por workload", "Quanto memória cada workload reserva?"),
        (numeric.build_memory_limit_chart, "mem_limit", "Memória limit por workload", "Qual o limit de memória por pod?"),
        (numeric.build_memory_request_limit_chart, "mem_request_limit", "Memória request × limit", "Como request e limit se comparam?"),
    ):
        chart = builder(bundle)
        if chart:
            specs.append(_spec_from_numeric(viz_id, "memory", chart))
        else:
            specs.append(
                _unavailable(viz_id, title, question, "memory", "Valores de memória não disponíveis nos Deployments.")
            )

    # §8 — QoS
    if qos_chart:
        specs.append(_spec_from_composition("qos_distribution_detail", "qos", qos_chart))
    else:
        specs.append(
            _unavailable(
                "qos_distribution_detail",
                "Distribuição de QoS",
                "Como workloads se distribuem por QoS?",
                "qos",
                "Classes QoS indisponíveis (Pods ausentes ou sem status.qosClass).",
                dataset_kind="composition",
            )
        )

    # §13 — workload × worknode
    placement = workload.build_workload_node_diagram(bundle)
    if placement:
        specs.append(_spec_from_flowchart("workload_node_placement", "workload_node", placement))
    else:
        specs.append(
            _unavailable(
                "workload_node_placement",
                "Placement workload × worknode",
                "Onde os pods estão alocados?",
                "workload_node",
                "Placement indisponível (arquivos de Pod ausentes ou sem spec.nodeName).",
                dataset_kind="flowchart",
            )
        )

    # §15 — findings
    severity = composition.build_severity_distribution(bundle)
    if severity:
        specs.append(_spec_from_composition("findings_severity", "findings", severity))
    category = composition.build_category_distribution(bundle)
    if category:
        specs.append(_spec_from_composition("findings_category", "findings", category))

    app_groups = composition.build_workloads_by_app_group(bundle)
    if app_groups:
        specs.append(_spec_from_composition("workloads_app_group", "workloads", app_groups))

    return VisualizationBundle(visualizations=tuple(specs))
