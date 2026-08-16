"""Testes de normalização de quantidades."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubeoptix_analyzer.errors import ParseError
from kubeoptix_analyzer.models.source import DataSourceRef
from kubeoptix_analyzer.normalize.quantities import parse_cpu_quantity, parse_memory_quantity

SOURCE = DataSourceRef(
    file_path="/tmp/test.yaml",
    resource_kind="Deployment",
    resource_name="test",
    namespace="test-ns",
)


class TestParseCpuQuantity:
    def test_millicores(self) -> None:
        qty = parse_cpu_quantity("350m", source=SOURCE, field_path="spec.cpu")
        assert qty.normalized_value == 350.0
        assert qty.raw == "350m"
        assert qty.source.field_path == "spec.cpu"
        assert qty.source.raw_value == "350m"

    def test_cores(self) -> None:
        qty = parse_cpu_quantity("8", source=SOURCE, field_path="status.capacity.cpu")
        assert qty.normalized_value == 8000.0

    def test_nanocores(self) -> None:
        qty = parse_cpu_quantity("6365928n", source=SOURCE, field_path="usage.cpu")
        assert abs(qty.normalized_value - 6.365928) < 0.001

    def test_invalid(self) -> None:
        with pytest.raises(ParseError):
            parse_cpu_quantity("invalid", source=SOURCE, field_path="spec.cpu")


class TestParseMemoryQuantity:
    def test_mebibytes(self) -> None:
        qty = parse_memory_quantity("384Mi", source=SOURCE, field_path="spec.memory")
        assert qty.normalized_value == 384 * 1024**2
        assert qty.raw == "384Mi"

    def test_gibibytes(self) -> None:
        qty = parse_memory_quantity("2Gi", source=SOURCE, field_path="spec.memory")
        assert qty.normalized_value == 2 * 1024**3

    def test_kibibytes(self) -> None:
        qty = parse_memory_quantity("841428Ki", source=SOURCE, field_path="usage.memory")
        assert qty.normalized_value == 841428 * 1024

    def test_invalid(self) -> None:
        with pytest.raises(ParseError):
            parse_memory_quantity("bad-value", source=SOURCE, field_path="spec.memory")
