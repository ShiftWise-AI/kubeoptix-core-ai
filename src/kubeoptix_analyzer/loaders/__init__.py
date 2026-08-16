"""Carregadores de dados."""

from kubeoptix_analyzer.loaders.workload_loader import WorkloadLoader
from kubeoptix_analyzer.loaders.worknode_loader import WorknodeLoader

__all__ = ["WorkloadLoader", "WorknodeLoader"]
