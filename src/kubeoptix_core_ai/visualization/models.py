"""Modelos de dados para gráficos e diagramas Mermaid."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceKind(str, Enum):
    """Classificação da origem de um valor na visualização."""

    OBSERVED = "observed"
    CALCULATED = "calculated"
    MATCHED = "matched"


class ProvenanceRef(BaseModel):
    """Rastreabilidade de um valor até o artefato de origem."""

    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    file_path: str | None = None
    field_path: str | None = None
    resource_kind: str | None = None
    resource_name: str | None = None
    description: str | None = None


class ChartPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    value: float
    unit: str
    provenance: tuple[ProvenanceRef, ...] = ()


class ChartSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    points: tuple[ChartPoint, ...]
    series_type: Literal["bar", "line"] = "bar"


class ChartDataset(BaseModel):
    """Dataset para gráficos numéricos (xychart-beta)."""

    model_config = ConfigDict(frozen=True)

    title: str
    question: str
    x_labels: tuple[str, ...]
    series: tuple[ChartSeries, ...]
    y_axis_label: str
    y_max: float | None = None


class PieSlice(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    value: float
    provenance: tuple[ProvenanceRef, ...] = ()


class CompositionDataset(BaseModel):
    """Dataset para gráficos de composição (pie)."""

    model_config = ConfigDict(frozen=True)

    title: str
    question: str
    slices: tuple[PieSlice, ...]


class DiagramNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    node_type: str
    label: str
    provenance: tuple[ProvenanceRef, ...] = ()


class DiagramEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    target_id: str
    edge_type: str
    label: str | None = None
    evidence: tuple[ProvenanceRef, ...] = ()


class FlowchartDataset(BaseModel):
    """Dataset para diagramas de arquitetura e comunicação."""

    model_config = ConfigDict(frozen=True)

    title: str
    question: str
    direction: Literal["LR", "TB"] = "LR"
    nodes: tuple[DiagramNode, ...]
    edges: tuple[DiagramEdge, ...]


class VisualizationStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class VisualizationSpec(BaseModel):
    """Especificação de uma visualização no relatório."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    question: str
    section: str
    status: VisualizationStatus
    mermaid: str | None = None
    interpretation: str = ""
    unavailable_reason: str | None = None
    provenance: tuple[ProvenanceRef, ...] = ()
    dataset_kind: Literal["numeric", "composition", "flowchart"] = "numeric"


class VisualizationBundle(BaseModel):
    """Conjunto de visualizações produzidas para um assessment."""

    model_config = ConfigDict(frozen=True)

    visualizations: tuple[VisualizationSpec, ...] = ()

    def by_section(self, section: str) -> tuple[VisualizationSpec, ...]:
        return tuple(v for v in self.visualizations if v.section == section)

    def by_id(self, viz_id: str) -> VisualizationSpec | None:
        for viz in self.visualizations:
            if viz.id == viz_id:
                return viz
        return None
