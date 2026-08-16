"""Configuração centralizada de caminhos e parâmetros do agente."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from kubeoptix_analyzer.errors import ConfigurationError

# Caminhos relativos ao diretório de trabalho — portáveis entre ambientes.
DEFAULT_WORKLOADS_BASE = Path("data/metadados")
DEFAULT_WORKNODES_PATH = Path("data/worknodes")

ENV_WORKLOADS_BASE = "KUBEOPTIX_WORKLOADS_BASE"
ENV_WORKNODES_PATH = "KUBEOPTIX_WORKNODES_PATH"
ENV_ML_ENABLED = "KUBEOPTIX_ML_ENABLED"
ENV_ML_SEED = "KUBEOPTIX_ML_SEED"

_VALID_NAMESPACE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")


@dataclass(frozen=True)
class AnalyzerConfig:
    """Configuração imutável do analisador."""

    workloads_base: Path = field(default_factory=lambda: DEFAULT_WORKLOADS_BASE)
    worknodes_path: Path = field(default_factory=lambda: DEFAULT_WORKNODES_PATH)

    @classmethod
    def from_env(cls) -> AnalyzerConfig:
        """Carrega configuração a partir de variáveis de ambiente."""
        return cls(
            workloads_base=Path(
                os.environ.get(ENV_WORKLOADS_BASE, str(DEFAULT_WORKLOADS_BASE))
            ),
            worknodes_path=Path(
                os.environ.get(ENV_WORKNODES_PATH, str(DEFAULT_WORKNODES_PATH))
            ),
        )

    def namespace_path(self, namespace: str) -> Path:
        """Retorna o diretório de um namespace dentro da base de workloads."""
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
