"""Carregador de worknodes."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_analyzer.config import AnalyzerConfig
from kubeoptix_analyzer.errors import ConfigurationError, ParseError
from kubeoptix_analyzer.logging import get_logger
from kubeoptix_analyzer.models.node import WorkNode, WorkNodeBundle
from kubeoptix_analyzer.parsers.node import parse_node

logger = get_logger("loaders.worknode")


class WorknodeLoader:
    """Carrega e normaliza worknodes a partir de arquivos Node YAML."""

    def __init__(self, config: AnalyzerConfig | None = None) -> None:
        self._config = config or AnalyzerConfig.from_env()

    def load(self, worknodes_path: Path | None = None) -> WorkNodeBundle:
        """Carrega todos os worknodes do diretório configurado."""
        path = worknodes_path or self._config.worknodes_path
        if not path.is_dir():
            raise ConfigurationError(f"Diretório de worknodes não encontrado: {path}")

        nodes: list[WorkNode] = []
        parse_errors: list[str] = []

        for node_file in sorted(path.glob("*.yaml")):
            try:
                nodes.append(parse_node(node_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear Node %s: %s", node_file, msg)

        return WorkNodeBundle(
            nodes=tuple(sorted(nodes, key=lambda n: n.name)),
            parse_errors=tuple(parse_errors),
        )
