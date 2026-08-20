"""Carregador de worknodes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.errors import ConfigurationError, ParseError
from kubeoptix_core_ai.logging import get_logger
from kubeoptix_core_ai.models.node import WorkNode, WorkNodeBundle
from kubeoptix_core_ai.parsers.node import parse_node

logger = get_logger("loaders.worknode")


class WorknodeLoader:
    """Carrega e normaliza worknodes a partir de arquivos Node YAML."""

    def __init__(self, config: AnalyzerConfig | None = None) -> None:
        self._config = config or AnalyzerConfig.from_env()

    def load(
        self,
        worknodes_path: Path | None = None,
        *,
        on_file_processed: Callable[[int, int], None] | None = None,
    ) -> WorkNodeBundle:
        """Carrega todos os worknodes do diretório configurado."""
        path = worknodes_path or self._config.worknodes_path
        if not path.is_dir():
            raise ConfigurationError(f"Diretório de worknodes não encontrado: {path}")

        nodes: list[WorkNode] = []
        parse_errors: list[str] = []
        node_files = sorted(path.glob("*.yaml"))
        total = len(node_files)

        for index, node_file in enumerate(node_files, start=1):
            try:
                nodes.append(parse_node(node_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear Node %s: %s", node_file, msg)
            if on_file_processed is not None:
                on_file_processed(index, total)

        return WorkNodeBundle(
            nodes=tuple(sorted(nodes, key=lambda n: n.name)),
            parse_errors=tuple(parse_errors),
        )
