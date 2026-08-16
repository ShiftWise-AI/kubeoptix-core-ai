"""Camada de análise determinística."""

__all__ = ["AnalysisEngine"]


def __getattr__(name: str):
    if name == "AnalysisEngine":
        from kubeoptix_core_ai.analysis.engine import AnalysisEngine

        return AnalysisEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
