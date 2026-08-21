"""Referências de comunicação extraídas dos YAMLs de workload (sem inferência)."""

from __future__ import annotations

import re
from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.workload import Workload
from kubeoptix_core_ai.parsers.base import load_yaml_file

_DATABASE_SECRET_MARKERS = (
    "database",
    "db-",
    "-db",
    "jdbc",
    "postgres",
    "oracle",
    "mysql",
    "mongo",
    "mariadb",
    "sql",
)

_SERVICE_REF_PATTERNS = (
    re.compile(r"https?://([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)(?::|/|$)", re.I),
    re.compile(
        r"\b([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\.[a-z0-9][a-z0-9.-]*\.svc(?:\.cluster\.local)?\b",
        re.I,
    ),
    re.compile(r"\b([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\.svc(?:\.cluster\.local)?\b", re.I),
)


def load_deployment_document(workload: Workload) -> dict | None:
    try:
        return load_yaml_file(Path(workload.source.file_path))
    except (OSError, ParseError):
        return None


def container_specs(workload: Workload) -> list[dict]:
    document = load_deployment_document(workload)
    if not document:
        return []
    template_spec = ((document.get("spec") or {}).get("template") or {}).get("spec") or {}
    containers = template_spec.get("containers") or []
    return [c for c in containers if isinstance(c, dict)]


def is_database_secret_name(name: str) -> bool:
    lower = name.lower()
    return any(marker in lower for marker in _DATABASE_SECRET_MARKERS)


def extract_database_refs(workload: Workload) -> tuple[tuple[str, str], ...]:
    """Referências a banco de dados via nome de Secret no YAML (sem ler conteúdo)."""
    refs: list[tuple[str, str]] = []
    for c_idx, container in enumerate(container_specs(workload)):
        for ef_idx, env_from in enumerate(container.get("envFrom") or []):
            if not isinstance(env_from, dict):
                continue
            secret_ref = env_from.get("secretRef")
            if not isinstance(secret_ref, dict):
                continue
            name = secret_ref.get("name")
            if not name or not is_database_secret_name(str(name)):
                continue
            field_path = (
                f"spec.template.spec.containers[{c_idx}].envFrom[{ef_idx}].secretRef"
            )
            refs.append((str(name), field_path))
        for e_idx, env in enumerate(container.get("env") or []):
            if not isinstance(env, dict):
                continue
            value = env.get("value")
            if not isinstance(value, str):
                continue
            if "jdbc:" in value.lower() or "database" in value.lower():
                refs.append(
                    (
                        value[:48],
                        f"spec.template.spec.containers[{c_idx}].env[{e_idx}].value",
                    )
                )
    return tuple(refs)


def extract_service_calls(
    workload: Workload,
    service_names: set[str],
) -> tuple[tuple[str, str, str], ...]:
    """Chamadas a Services internos evidenciadas em variáveis de ambiente."""
    names_by_lower = {name.lower(): name for name in service_names}
    calls: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    for c_idx, container in enumerate(container_specs(workload)):
        for e_idx, env in enumerate(container.get("env") or []):
            if not isinstance(env, dict):
                continue
            value = env.get("value")
            if not isinstance(value, str):
                continue
            env_name = str(env.get("name", ""))
            field_path = f"spec.template.spec.containers[{c_idx}].env[{e_idx}].value"
            for pattern in _SERVICE_REF_PATTERNS:
                for match in pattern.finditer(value):
                    canonical = names_by_lower.get(match.group(1).lower())
                    if canonical is None:
                        continue
                    if canonical.lower() == workload.name.lower():
                        continue
                    key = (canonical, field_path)
                    if key in seen:
                        continue
                    seen.add(key)
                    calls.append((canonical, field_path, env_name))
    return tuple(calls)


def extract_cross_namespace_service_refs(
    workload: Workload,
) -> tuple[tuple[str, str, str], ...]:
    """Secrets/ConfigMaps em outros namespaces referenciados explicitamente no YAML."""
    refs: list[tuple[str, str, str]] = []
    for c_idx, container in enumerate(container_specs(workload)):
        for e_idx, env in enumerate(container.get("env") or []):
            if not isinstance(env, dict):
                continue
            value_from = env.get("valueFrom")
            if not isinstance(value_from, dict):
                continue
            for ref_key in ("configMapKeyRef", "secretKeyRef"):
                if ref_key not in value_from or not isinstance(value_from[ref_key], dict):
                    continue
                ref = value_from[ref_key]
                other_ns = ref.get("namespace")
                name = ref.get("name")
                if not other_ns or not name or other_ns == workload.namespace:
                    continue
                if not is_database_secret_name(str(name)):
                    continue
                field_path = (
                    f"spec.template.spec.containers[{c_idx}].env[{e_idx}]"
                    f".valueFrom.{ref_key}"
                )
                refs.append((str(other_ns), str(name), field_path))
    return tuple(refs)
