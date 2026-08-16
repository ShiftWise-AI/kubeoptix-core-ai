"""Conversão de strings de CPU e memória para valores normalizados."""

from __future__ import annotations

import re

from kubeoptix_analyzer.errors import ParseError
from kubeoptix_analyzer.models.quantities import ResourceQuantity
from kubeoptix_analyzer.models.source import DataSourceRef, FieldRef

_CPU_MILLICORES = re.compile(r"^(\d+(?:\.\d+)?)m$")
_CPU_CORES = re.compile(r"^(\d+(?:\.\d+)?)$")
_CPU_NANOCORES = re.compile(r"^(\d+(?:\.\d+)?)n$")

_MEMORY_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(Ki|Mi|Gi|Ti|K|M|G|T|Pi|E|P)?$",
    re.IGNORECASE,
)

_BINARY_SUFFIXES = {
    "ki": 1024,
    "mi": 1024**2,
    "gi": 1024**3,
    "ti": 1024**4,
    "pi": 1024**5,
    "ei": 1024**6,
}

_DECIMAL_SUFFIXES = {
    "k": 1000,
    "m": 1000**2,
    "g": 1000**3,
    "t": 1000**4,
    "p": 1000**5,
    "e": 1000**6,
}


def _field_ref(source: DataSourceRef, field_path: str, raw: str) -> FieldRef:
    return FieldRef(file_path=source.file_path, field_path=field_path, raw_value=raw)


def parse_cpu_quantity(
    raw: str | int | float,
    *,
    source: DataSourceRef,
    field_path: str,
) -> ResourceQuantity:
    """Converte valor de CPU Kubernetes para millicores."""
    text = str(raw).strip()
    if not text:
        raise ParseError(f"CPU vazio em {field_path}", file_path=None)

    millicores: float
    display_unit = "m"

    if match := _CPU_MILLICORES.match(text):
        millicores = float(match.group(1))
    elif match := _CPU_NANOCORES.match(text):
        millicores = float(match.group(1)) / 1_000_000
        display_unit = "n"
    elif match := _CPU_CORES.match(text):
        millicores = float(match.group(1)) * 1000
        display_unit = "cores"
    else:
        raise ParseError(
            f"Formato de CPU não reconhecido: {text!r}",
            file_path=None,
        )

    return ResourceQuantity(
        raw=text,
        resource_kind="cpu",
        normalized_value=millicores,
        display_unit=display_unit,
        source=_field_ref(source, field_path, text),
    )


def parse_memory_quantity(
    raw: str | int,
    *,
    source: DataSourceRef,
    field_path: str,
) -> ResourceQuantity:
    """Converte valor de memória Kubernetes para bytes."""
    text = str(raw).strip()
    if not text:
        raise ParseError(f"Memória vazia em {field_path}", file_path=None)

    match = _MEMORY_PATTERN.match(text)
    if not match:
        raise ParseError(
            f"Formato de memória não reconhecido: {text!r}",
            file_path=None,
        )

    value = float(match.group(1))
    suffix = (match.group(2) or "").lower()

    if suffix in _BINARY_SUFFIXES:
        bytes_value = value * _BINARY_SUFFIXES[suffix]
        display_unit = suffix
    elif suffix in _DECIMAL_SUFFIXES:
        bytes_value = value * _DECIMAL_SUFFIXES[suffix]
        display_unit = suffix
    elif suffix == "":
        bytes_value = value
        display_unit = "bytes"
    else:
        raise ParseError(
            f"Sufixo de memória não reconhecido: {suffix!r}",
            file_path=None,
        )

    return ResourceQuantity(
        raw=text,
        resource_kind="memory",
        normalized_value=bytes_value,
        display_unit=display_unit,
        source=_field_ref(source, field_path, text),
    )
