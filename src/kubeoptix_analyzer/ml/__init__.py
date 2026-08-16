"""Camada de análise estatística e ML local (CPU only, offline)."""

from kubeoptix_analyzer.ml.config import MLConfig

__all__ = ["MLConfig", "MLEngine"]


def __getattr__(name: str):
    if name == "MLEngine":
        from kubeoptix_analyzer.ml.engine import MLEngine

        return MLEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
