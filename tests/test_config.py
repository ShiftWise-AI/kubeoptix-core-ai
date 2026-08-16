"""Testes de configuração de caminhos."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.errors import ConfigurationError

FIXTURES = Path(__file__).parent / "fixtures"


def _write_minimal_namespace(base: Path, name: str) -> None:
    app = base / name / "apps" / "backend-acesso-app" / "deployments"
    app.mkdir(parents=True)
    shutil.copy(FIXTURES / "deployment_backend_acesso_app.yaml", app / "app.yaml")


def test_from_metadata_dir_resolves_sibling_worknodes(tmp_path: Path) -> None:
    metadata = tmp_path / "metadados"
    metadata.mkdir()
    _write_minimal_namespace(metadata, "example-ns-prd")

    worknodes = tmp_path / "worknodes"
    worknodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", worknodes / "node.yaml")

    config = AnalyzerConfig.from_metadata_dir(metadata)

    assert config.workloads_base == metadata.resolve()
    assert config.worknodes_path == worknodes.resolve()


def test_from_metadata_dir_resolves_nested_worknodes(tmp_path: Path) -> None:
    metadata = tmp_path / "metadados"
    metadata.mkdir()
    _write_minimal_namespace(metadata, "example-ns-prd")

    worknodes = metadata / "worknodes"
    worknodes.mkdir()
    shutil.copy(FIXTURES / "node_osc3dv0117.yaml", worknodes / "node.yaml")

    config = AnalyzerConfig.from_metadata_dir(metadata)

    assert config.worknodes_path == worknodes.resolve()


def test_from_metadata_dir_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="metadados não encontrado"):
        AnalyzerConfig.from_metadata_dir(tmp_path / "missing")


def test_from_metadata_dir_without_worknodes_raises(tmp_path: Path) -> None:
    metadata = tmp_path / "metadados"
    metadata.mkdir()
    _write_minimal_namespace(metadata, "example-ns-prd")

    with pytest.raises(ConfigurationError, match="worknodes não encontrado"):
        AnalyzerConfig.from_metadata_dir(metadata)
