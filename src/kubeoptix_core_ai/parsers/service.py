"""Parser de Services (v1)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.inventory import ServicePortSpec, ServiceSpec
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.parsers.base import load_yaml_file


def parse_service(file_path: Path) -> ServiceSpec:
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "Service":
        raise ParseError(f"kind esperado 'Service', encontrado {kind!r}", file_path=file_path)

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}

    ports: list[ServicePortSpec] = []
    for port_data in spec.get("ports") or []:
        if not isinstance(port_data, dict):
            continue
        target = port_data.get("targetPort")
        if target is not None and not isinstance(target, (int, str)):
            target = str(target)
        port_val = port_data.get("port")
        ports.append(
            ServicePortSpec(
                name=port_data.get("name"),
                port=int(port_val) if port_val is not None else None,
                target_port=target,
                protocol=port_data.get("protocol"),
            )
        )

    selector_raw = spec.get("selector") or {}
    selector = (
        {str(k): str(v) for k, v in selector_raw.items()}
        if isinstance(selector_raw, dict)
        else {}
    )

    return ServiceSpec(
        name=str(metadata.get("name", file_path.stem)),
        namespace=str(metadata.get("namespace", "")),
        service_type=spec.get("type"),
        cluster_ip=spec.get("clusterIP"),
        selector=selector,
        ports=tuple(ports),
        session_affinity=spec.get("sessionAffinity"),
        source=source,
    )
