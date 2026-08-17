"""Parser de Deployments (apps/v1) — compatibilidade com API legada."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.models.workload import Workload
from kubeoptix_core_ai.parsers.workload_controller import parse_workload_controller


def parse_deployment(file_path: Path, *, app_group: str | None = None) -> Workload:
    """Interpreta um arquivo YAML de Deployment."""
    return parse_workload_controller(
        file_path,
        app_group=app_group,
        expected_kind="Deployment",
    )
