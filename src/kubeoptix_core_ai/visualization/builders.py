"""Builders que convertem datasets em VisualizationSpec."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.report.i18n import translate_report, validate_locale
from kubeoptix_core_ai.report.pipeline import AssessmentBundle
from kubeoptix_core_ai.visualization.datasets import communication, composition, numeric, workload
from kubeoptix_core_ai.visualization.diagram_renderer import DiagramRenderer
from kubeoptix_core_ai.visualization.interpretation import interpret_visualization
from kubeoptix_core_ai.visualization.kubediagrams.mapping import (
    manifest_index_for,
    manifests_for_external_route,
    manifests_for_internal_service,
    manifests_for_workload_dependencies,
    manifests_for_workload_group,
    manifests_for_workload_node_placement,
)
from kubeoptix_core_ai.visualization.models import (
    ChartDataset,
    CompositionDataset,
    FlowchartDataset,
    ProvenanceRef,
    VisualizationSpec,
    VisualizationStatus,
    VisualizationBundle,
)
from kubeoptix_core_ai.visualization.png import PngRenderer


def _localize_numeric(dataset: ChartDataset, locale: str) -> ChartDataset:
    return dataset.model_copy(
        update={
            "title": translate_report(dataset.title, locale),
            "question": translate_report(dataset.question, locale),
            "x_labels": tuple(translate_report(label, locale) for label in dataset.x_labels),
            "x_axis_label": translate_report(dataset.x_axis_label, locale),
            "y_axis_label": translate_report(dataset.y_axis_label, locale),
            "series": tuple(
                series.model_copy(
                    update={
                        "name": translate_report(series.name, locale),
                        "points": tuple(
                            point.model_copy(
                                update={"label": translate_report(point.label, locale)}
                            )
                            for point in series.points
                        ),
                    }
                )
                for series in dataset.series
            ),
        }
    )


def _localize_composition(
    dataset: CompositionDataset, locale: str
) -> CompositionDataset:
    return dataset.model_copy(
        update={
            "title": translate_report(dataset.title, locale),
            "question": translate_report(dataset.question, locale),
            "slices": tuple(
                slice_.model_copy(
                    update={"label": translate_report(slice_.label, locale)}
                )
                for slice_ in dataset.slices
            ),
        }
    )


def _localize_flowchart(dataset: FlowchartDataset, locale: str) -> FlowchartDataset:
    return dataset.model_copy(
        update={
            "title": translate_report(dataset.title, locale),
            "question": translate_report(dataset.question, locale),
            "nodes": tuple(
                node.model_copy(
                    update={"label": translate_report(node.label, locale)}
                )
                for node in dataset.nodes
            ),
            "edges": tuple(
                edge.model_copy(
                    update={
                        "label": (
                            translate_report(edge.label, locale)
                            if edge.label is not None
                            else None
                        )
                    }
                )
                for edge in dataset.edges
            ),
            "subgraphs": tuple(
                subgraph.model_copy(
                    update={"title": translate_report(subgraph.title, locale)}
                )
                for subgraph in dataset.subgraphs
            ),
        }
    )


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
    renderer: PngRenderer | None,
    locale: str,
) -> VisualizationSpec:
    dataset = _localize_numeric(dataset, locale)
    image_relpath = renderer.render_numeric(viz_id, dataset) if renderer else None
    provenance = _collect_provenance_numeric(dataset)
    interpretation = interpret_visualization(dataset)
    return VisualizationSpec(
        id=viz_id,
        title=dataset.title,
        question=dataset.question,
        section=section,
        status=VisualizationStatus.AVAILABLE,
        image_relpath=image_relpath,
        interpretation=interpretation,
        provenance=provenance,
        dataset_kind="numeric",
    )


def _spec_from_composition(
    viz_id: str,
    section: str,
    dataset: CompositionDataset,
    renderer: PngRenderer | None,
    locale: str,
) -> VisualizationSpec:
    dataset = _localize_composition(dataset, locale)
    image_relpath = renderer.render_composition(viz_id, dataset) if renderer else None
    provenance = _collect_provenance_composition(dataset)
    interpretation = interpret_visualization(dataset)
    return VisualizationSpec(
        id=viz_id,
        title=dataset.title,
        question=dataset.question,
        section=section,
        status=VisualizationStatus.AVAILABLE,
        image_relpath=image_relpath,
        interpretation=interpretation,
        provenance=provenance,
        dataset_kind="composition",
    )


def _spec_from_flowchart(
    viz_id: str,
    section: str,
    dataset: FlowchartDataset,
    manifests: tuple[Path, ...],
    diagram_renderer: DiagramRenderer | None,
    locale: str,
) -> VisualizationSpec:
    dataset = _localize_flowchart(dataset, locale)
    provenance = _collect_provenance_flowchart(dataset)
    interpretation = interpret_visualization(dataset)

    image_relpath: str | None = None
    diagram_engine = None
    yaml_sources: tuple[str, ...] = ()

    if diagram_renderer is not None:
        result = diagram_renderer.render_flowchart(viz_id, manifests, dataset)
        image_relpath = result.image_relpath
        diagram_engine = result.engine
        yaml_sources = result.yaml_sources
        failure_reason = result.failure_reason
    else:
        failure_reason = None

    if image_relpath is None:
        reason_text = (
            f"renderização indisponível ({failure_reason})."
            if failure_reason
            else "renderização indisponível."
        )
        return VisualizationSpec(
            id=viz_id,
            title=dataset.title,
            question=dataset.question,
            section=section,
            status=VisualizationStatus.UNAVAILABLE,
            unavailable_reason=(
                "Diagrama não gerado: "
                f"{reason_text} "
                "Não há manifests YAML suficientes para renderização."
            ),
            interpretation=(
                "**Limitação:** "
                f"{reason_text} "
                "Não há manifests YAML suficientes para renderização."
            ),
            provenance=provenance,
            dataset_kind="flowchart",
        )

    return VisualizationSpec(
        id=viz_id,
        title=dataset.title,
        question=dataset.question,
        section=section,
        status=VisualizationStatus.AVAILABLE,
        image_relpath=image_relpath,
        diagram_engine=diagram_engine,
        yaml_sources=yaml_sources,
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
    locale: str = "pt-BR",
) -> VisualizationSpec:
    return VisualizationSpec(
        id=viz_id,
        title=translate_report(title, locale),
        question=translate_report(question, locale),
        section=section,
        status=VisualizationStatus.UNAVAILABLE,
        unavailable_reason=translate_report(reason, locale),
        interpretation=translate_report(f"**Limitação:** {reason}", locale),
        dataset_kind=dataset_kind,  # type: ignore[arg-type]
    )


def build_all_visualizations(
    bundle: AssessmentBundle,
    renderer: PngRenderer | None = None,
    diagram_renderer: DiagramRenderer | None = None,
    locale: str = "pt-BR",
) -> VisualizationBundle:
    locale = validate_locale(locale)
    specs: list[VisualizationSpec] = []
    index = manifest_index_for(bundle) if diagram_renderer is not None else None

    # §4 — visão geral
    ns_chart = numeric.build_namespace_requests_vs_allocatable(bundle)
    if ns_chart:
        specs.append(_spec_from_numeric("ns_requests_allocatable", "namespace_overview", ns_chart, renderer, locale))
    else:
        specs.append(
            _unavailable(
                "ns_requests_allocatable",
                "Requests do namespace × capacidade allocatable",
                "Os requests agregados cabem no pool de scheduling?",
                "namespace_overview",
                "Dados de request do namespace ou capacidade allocatable do pool indisponíveis.",
                locale=locale,
            )
        )

    qos_chart = composition.build_qos_distribution(bundle)
    if qos_chart:
        specs.append(_spec_from_composition("qos_distribution", "namespace_overview", qos_chart, renderer, locale))

    # §5 — workloads
    workload_groups = workload.iter_workload_diagram_groups(bundle)
    if workload_groups:
        for idx, (diagram, group_workloads) in enumerate(workload_groups):
            manifests = ()
            if index is not None:
                manifests = manifests_for_workload_group(group_workloads, bundle, index)
            specs.append(
                _spec_from_flowchart(
                    f"workload_diagram_{idx}",
                    "workloads",
                    diagram,
                    manifests,
                    diagram_renderer,
                    locale,
                )
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
                locale=locale,
            )
        )

    external_diagrams = communication.build_external_communication_diagrams(bundle)
    if external_diagrams:
        for diagram in external_diagrams:
            route_key = diagram.title.rsplit(" — ", 1)[-1]
            route = next((r for r in bundle.context.routes if r.name == route_key), None)
            manifests = ()
            if index is not None and route is not None:
                manifests = manifests_for_external_route(route, bundle, index)
            specs.append(
                _spec_from_flowchart(
                    f"ext_comm_{route_key}",
                    "communication_external",
                    diagram,
                    manifests,
                    diagram_renderer,
                    locale,
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
                locale=locale,
            )
        )

    internal_diagrams = communication.build_internal_communication_diagrams(bundle)
    if internal_diagrams:
        for diagram in internal_diagrams:
            svc_key = diagram.title.rsplit(" — ", 1)[-1]
            service = next((s for s in bundle.context.services if s.name == svc_key), None)
            manifests = ()
            if index is not None and service is not None:
                manifests = manifests_for_internal_service(service, bundle, index)
            specs.append(
                _spec_from_flowchart(
                    f"int_comm_{svc_key}",
                    "communication_internal",
                    diagram,
                    manifests,
                    diagram_renderer,
                    locale,
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
                locale=locale,
            )
        )

    dependency_diagrams = communication.build_external_dependencies_diagrams(bundle)
    if dependency_diagrams:
        for diagram in dependency_diagrams:
            wl_key = diagram.title.rsplit(" — ", 1)[-1]
            wl = next((w for w in bundle.context.workloads if w.name == wl_key), None)
            manifests = ()
            if index is not None and wl is not None:
                manifests = manifests_for_workload_dependencies(wl, bundle, index)
            specs.append(
                _spec_from_flowchart(
                    f"ext_dep_{wl_key}",
                    "communication_dependencies",
                    diagram,
                    manifests,
                    diagram_renderer,
                    locale,
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
                locale=locale,
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
            specs.append(_spec_from_numeric(viz_id, "cpu", chart, renderer, locale))
        else:
            specs.append(
                _unavailable(viz_id, title, question, "cpu", "Valores de CPU não disponíveis nos workloads.", locale=locale)
            )

    # §7 — memória
    for builder, viz_id, title, question in (
        (numeric.build_memory_request_chart, "mem_request", "Memória request por workload", "Quanto memória cada workload reserva?"),
        (numeric.build_memory_limit_chart, "mem_limit", "Memória limit por workload", "Qual o limit de memória por pod?"),
        (numeric.build_memory_request_limit_chart, "mem_request_limit", "Memória request × limit", "Como request e limit se comparam?"),
    ):
        chart = builder(bundle)
        if chart:
            specs.append(_spec_from_numeric(viz_id, "memory", chart, renderer, locale))
        else:
            specs.append(
                _unavailable(viz_id, title, question, "memory", "Valores de memória não disponíveis nos workloads.", locale=locale)
            )

    # §8 — QoS
    if qos_chart:
        specs.append(_spec_from_composition("qos_distribution_detail", "qos", qos_chart, renderer, locale))
    else:
        specs.append(
            _unavailable(
                "qos_distribution_detail",
                "Distribuição de QoS",
                "Como workloads se distribuem por QoS?",
                "qos",
                "Classes QoS indisponíveis (Pods ausentes ou sem status.qosClass).",
                dataset_kind="composition",
                locale=locale,
            )
        )

    # §13 — workload × worknode
    placement = workload.build_workload_node_diagram(bundle)
    if placement:
        manifests = ()
        if index is not None:
            manifests = manifests_for_workload_node_placement(bundle, index)
        specs.append(
            _spec_from_flowchart(
                "workload_node_placement",
                "workload_node",
                placement,
                manifests,
                diagram_renderer,
                locale,
            )
        )
    else:
        specs.append(
            _unavailable(
                "workload_node_placement",
                "Placement workload × worknode",
                "Onde os pods estão alocados?",
                "workload_node",
                "Placement indisponível (arquivos de Pod ausentes ou sem spec.nodeName).",
                dataset_kind="flowchart",
                locale=locale,
            )
        )

    # §15 — findings
    severity = composition.build_severity_distribution(bundle)
    if severity:
        specs.append(_spec_from_composition("findings_severity", "findings", severity, renderer, locale))
    category = composition.build_category_distribution(bundle)
    if category:
        specs.append(_spec_from_composition("findings_category", "findings", category, renderer, locale))

    app_groups = composition.build_workloads_by_app_group(bundle)
    if app_groups:
        specs.append(_spec_from_composition("workloads_app_group", "workloads", app_groups, renderer, locale))

    return VisualizationBundle(visualizations=tuple(specs))
