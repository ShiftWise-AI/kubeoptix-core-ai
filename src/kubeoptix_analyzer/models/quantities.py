"""Quantidades de recursos (CPU e memória) com rastreabilidade."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from kubeoptix_analyzer.models.source import FieldRef

ResourceKind = Literal["cpu", "memory"]


class ResourceQuantity(BaseModel):
    """Valor de recurso preservando representação original e valor normalizado."""

    model_config = ConfigDict(frozen=True)

    raw: str
    resource_kind: ResourceKind
    # CPU: millicores; memória: bytes
    normalized_value: float
    display_unit: str
    source: FieldRef

    @property
    def millicores(self) -> float | None:
        if self.resource_kind == "cpu":
            return self.normalized_value
        return None

    @property
    def bytes_value(self) -> float | None:
        if self.resource_kind == "memory":
            return self.normalized_value
        return None
