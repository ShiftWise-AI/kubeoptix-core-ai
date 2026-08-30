"""Centralized configuration for agent paths and parameters."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from kubeoptix_core_ai.errors import ConfigurationError

# Relative paths from the working directory — portable across environments.
DEFAULT_WORKLOADS_BASE = Path("data/metadados")
DEFAULT_WORKNODES_PATH = Path("data/worknodes")

ENV_METADATA_DIR = "KUBEOPTIX_METADATA_DIR"
ENV_OUTPUT_DIR = "KUBEOPTIX_OUTPUT_DIR"
ENV_WORKLOADS_BASE = "KUBEOPTIX_WORKLOADS_BASE"
ENV_WORKNODES_PATH = "KUBEOPTIX_WORKNODES_PATH"
ENV_ML_ENABLED = "KUBEOPTIX_ML_ENABLED"
ENV_ML_SEED = "KUBEOPTIX_ML_SEED"

_VALID_NAMESPACE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")


def resolve_worknodes_path(metadata_dir: Path) -> Path:
    """Locate the worknodes directory relative to the metadata directory."""
    metadata_dir = metadata_dir.resolve()
    candidates = (
        metadata_dir / "worknodes",
        metadata_dir.parent / "worknodes",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise ConfigurationError(
        "Diretório de worknodes não encontrado. "
        f"Esperado em {candidates[0]} ou {candidates[1]}"
    )


@dataclass(frozen=True)
class AnalyzerConfig:
    """Immutable analyzer configuration."""

    workloads_base: Path = field(default_factory=lambda: DEFAULT_WORKLOADS_BASE)
    worknodes_path: Path = field(default_factory=lambda: DEFAULT_WORKNODES_PATH)

    @classmethod
    def from_env(cls) -> AnalyzerConfig:
        """Load configuration from environment variables."""
        metadata_dir = os.environ.get(ENV_METADATA_DIR)
        if metadata_dir:
            return cls.from_metadata_dir(Path(metadata_dir))

        workloads_base = Path(
            os.environ.get(ENV_WORKLOADS_BASE, str(DEFAULT_WORKLOADS_BASE))
        )
        if ENV_WORKNODES_PATH in os.environ:
            worknodes_path = Path(os.environ[ENV_WORKNODES_PATH])
        elif workloads_base.is_dir():
            try:
                worknodes_path = resolve_worknodes_path(workloads_base)
            except ConfigurationError:
                worknodes_path = DEFAULT_WORKNODES_PATH
        else:
            worknodes_path = DEFAULT_WORKNODES_PATH
        return cls(workloads_base=workloads_base, worknodes_path=worknodes_path)

    @classmethod
    def from_metadata_dir(cls, metadata_dir: Path) -> AnalyzerConfig:
        """Configure workloads and worknodes from the metadata directory."""
        path = Path(metadata_dir).resolve()
        if not path.is_dir():
            raise ConfigurationError(f"Diretório de metadados não encontrado: {path}")
        return cls(
            workloads_base=path,
            worknodes_path=resolve_worknodes_path(path),
        )

    def namespace_path(self, namespace: str) -> Path:
        """Return the namespace directory within the workloads base."""
        if not namespace or not _VALID_NAMESPACE.match(namespace):
            raise ConfigurationError(
                f"Nome de namespace inválido: {namespace!r}. "
                "Use apenas letras minúsculas, dígitos, hífens e pontos."
            )
        base = self.workloads_base.resolve()
        path = (base / namespace).resolve()
        if not path.is_relative_to(base):
            raise ConfigurationError(
                f"Nome de namespace inválido (path traversal): {namespace!r}"
            )
        return path
