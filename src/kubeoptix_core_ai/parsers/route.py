"""Parser de Routes OpenShift (route.openshift.io/v1)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.inventory import RouteSpec
from kubeoptix_core_ai.models.source import source_from_document
from kubeoptix_core_ai.parsers.base import load_yaml_file


def parse_route(file_path: Path) -> RouteSpec:
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "Route":
        raise ParseError(f"kind esperado 'Route', encontrado {kind!r}", file_path=file_path)

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}

    port_spec = spec.get("port") or {}
    target_port = port_spec.get("targetPort")
    if target_port is not None and not isinstance(target_port, (int, str)):
        target_port = str(target_port)

    tls = spec.get("tls") or {}
    to_spec = spec.get("to") or {}

    status = document.get("status") or {}
    ingress_list = status.get("ingress") or []
    router_name: str | None = None
    router_canonical_hostname: str | None = None
    if ingress_list and isinstance(ingress_list[0], dict):
        first_ingress = ingress_list[0]
        router_name = first_ingress.get("routerName")
        router_canonical_hostname = first_ingress.get("routerCanonicalHostname")

    return RouteSpec(
        name=str(metadata.get("name", file_path.stem)),
        namespace=str(metadata.get("namespace", "")),
        host=spec.get("host"),
        target_service=to_spec.get("name"),
        target_port=target_port,
        tls_termination=tls.get("termination"),
        tls_insecure_policy=tls.get("insecureEdgeTerminationPolicy"),
        wildcard_policy=spec.get("wildcardPolicy"),
        router_name=str(router_name) if router_name else None,
        router_canonical_hostname=str(router_canonical_hostname)
        if router_canonical_hostname
        else None,
        source=source,
    )
