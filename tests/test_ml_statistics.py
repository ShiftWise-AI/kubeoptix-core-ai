"""Testes unitários da análise estatística (z-score / IQR)."""

from __future__ import annotations

import math

import numpy as np

from kubeoptix_analyzer.ml.config import MLConfig
from kubeoptix_analyzer.ml.features import FEATURE_NAMES, FeatureMatrix
from kubeoptix_analyzer.ml.findings_builder import MLFindingBuilder
from kubeoptix_analyzer.ml.statistics import analyze_statistics


def _matrix(column_values: list[float], feature: str = "cpu_request_m") -> FeatureMatrix:
    idx = FEATURE_NAMES.index(feature)
    row = [0.0] * len(FEATURE_NAMES)
    row[idx] = 1.0  # placeholder for other columns
    matrix = np.array([row[:] for _ in column_values], dtype=np.float64)
    for i, val in enumerate(column_values):
        matrix[i, idx] = val
    return FeatureMatrix(
        workload_names=tuple(f"w{i}" for i in range(len(column_values))),
        matrix=matrix,
    )


def test_skips_all_nan_column() -> None:
    """Colunas de usage/request sem PodMetrics não devem quebrar z-score."""
    idx = FEATURE_NAMES.index("cpu_usage_request_ratio")
    matrix = np.full((5, len(FEATURE_NAMES)), float("nan"))
    matrix[:, 0] = [100, 200, 210, 190, 50000]  # cpu_request_m com outlier claro
    features = FeatureMatrix(
        workload_names=tuple(f"w{i}" for i in range(5)),
        matrix=matrix,
    )
    builder = MLFindingBuilder()
    analyze_statistics(features, "ns-test", MLConfig(), builder)
    assert builder.findings  # outlier em cpu_request_m
    assert all("cpu_usage_request_ratio" not in f.analysis for f in builder.findings)


def test_zscore_detects_outlier() -> None:
    features = _matrix([200, 210, 220, 190, 50000])
    builder = MLFindingBuilder()
    analyze_statistics(features, "ns-test", MLConfig(zscore_threshold=3.5), builder)
    outlier = [f for f in builder.findings if f.workload == "w4"]
    assert outlier
    assert outlier[0].category == "MLSTAT"


def test_no_findings_on_uniform_column() -> None:
    features = _matrix([500, 500, 500])
    builder = MLFindingBuilder()
    analyze_statistics(features, "ns-test", MLConfig(), builder)
    assert not builder.findings


def test_iqr_requires_four_finite_values() -> None:
    features = _matrix([10, 20, 30])  # menos de 4 para IQR
    builder = MLFindingBuilder()
    analyze_statistics(features, "ns-test", MLConfig(), builder)
    # z-score pode rodar com 3; IQR não
    iqr_findings = [f for f in builder.findings if "IQR" in f.analysis]
    assert not iqr_findings


def test_finite_values_ignore_nan() -> None:
    idx = FEATURE_NAMES.index("cpu_request_m")
    matrix = np.array(
        [
            [100.0 if j == idx else math.nan for j in range(len(FEATURE_NAMES))],
            [200.0 if j == idx else math.nan for j in range(len(FEATURE_NAMES))],
            [float("nan") if j == idx else math.nan for j in range(len(FEATURE_NAMES))],
        ],
        dtype=np.float64,
    )
    features = FeatureMatrix(
        workload_names=("a", "b", "c"),
        matrix=matrix,
    )
    builder = MLFindingBuilder()
    # Não deve lançar exceção com NaN parcial
    analyze_statistics(features, "ns-test", MLConfig(min_workloads_stat=2), builder)
