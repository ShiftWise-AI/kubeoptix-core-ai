"""Descoberta de arquivos."""

from kubeoptix_analyzer.discovery.scanner import (
    NamespacePaths,
    discover_namespace,
    list_namespace_dirs,
)

__all__ = ["NamespacePaths", "discover_namespace", "list_namespace_dirs"]
