"""Parser de ClusterServiceVersions (OLM) e PackageManifests."""

from __future__ import annotations

import re
from pathlib import Path

from kubeoptix_analyzer.errors import ParseError
from kubeoptix_analyzer.models.inventory import OperatorCSVSpec
from kubeoptix_analyzer.models.source import DataSourceRef, source_from_document
from kubeoptix_analyzer.parsers.base import load_yaml_file

_CSV_NAME_RE = re.compile(r"^(.+?)\.v[\d]")
_LINE_VALUE_RE = re.compile(r"^(\w+): (.+)$")


def _package_name_from_csv(csv_name: str) -> str:
    match = _CSV_NAME_RE.match(csv_name)
    return match.group(1) if match else csv_name


def _parse_csv_fallback(file_path: Path) -> OperatorCSVSpec:
    """Extrai campos essenciais quando o YAML completo é inválido (ex.: alm-examples)."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    fields: dict[str, str] = {}
    in_metadata = False
    in_spec = False
    in_status = False

    for line in text.splitlines():
        if line == "metadata:":
            in_metadata = True
            in_spec = False
            in_status = False
            continue
        if line == "spec:":
            in_spec = True
            in_metadata = False
            in_status = False
            continue
        if line == "status:":
            in_status = True
            in_metadata = False
            in_spec = False
            continue
        if line and not line.startswith(" ") and line.endswith(":"):
            in_metadata = False
            in_spec = False
            in_status = False

        stripped = line.strip()
        match = _LINE_VALUE_RE.match(stripped)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip().strip('"').strip("'")

        if in_metadata and key == "name" and line.startswith("  name:") and "name" not in fields:
            fields["name"] = value
        elif in_spec and key == "displayName" and line.startswith("  displayName:"):
            fields["displayName"] = value
        elif in_spec and key == "version" and line.startswith("  version:"):
            fields["version"] = value
        elif in_status and key == "phase" and line.startswith("  phase:"):
            fields["phase"] = value
        elif in_status and key == "reason" and line.startswith("  reason:"):
            fields["reason"] = value

    name = fields.get("name", file_path.stem)
    source = DataSourceRef(
        file_path=str(file_path),
        resource_kind="ClusterServiceVersion",
        resource_name=name,
    )
    return OperatorCSVSpec(
        name=name,
        display_name=fields.get("displayName"),
        version=fields.get("version"),
        phase=fields.get("phase"),
        reason=fields.get("reason"),
        package_name=_package_name_from_csv(name),
        source=source,
    )


def parse_clusterserviceversion(file_path: Path) -> OperatorCSVSpec:
    try:
        document = load_yaml_file(file_path)
    except ParseError:
        return _parse_csv_fallback(file_path)

    kind = document.get("kind")
    if kind != "ClusterServiceVersion":
        raise ParseError(
            f"kind esperado 'ClusterServiceVersion', encontrado {kind!r}",
            file_path=file_path,
        )

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    status = document.get("status") or {}

    name = str(metadata.get("name", file_path.stem))
    labels = metadata.get("labels") or {}
    provider = labels.get("provider") if isinstance(labels, dict) else None
    if not provider:
        provider = spec.get("provider", {}).get("name") if isinstance(spec.get("provider"), dict) else None

    return OperatorCSVSpec(
        name=name,
        display_name=spec.get("displayName"),
        version=spec.get("version"),
        provider=str(provider) if provider else None,
        phase=status.get("phase"),
        reason=status.get("reason"),
        package_name=_package_name_from_csv(name),
        source=source,
    )


def parse_packagemanifest(file_path: Path) -> tuple[str, str, str | None]:
    """
  Retorna (package_name, default_channel, current_csv do canal padrão).
    """
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "PackageManifest":
        raise ParseError(
            f"kind esperado 'PackageManifest', encontrado {kind!r}",
            file_path=file_path,
        )

    metadata = document.get("metadata") or {}
    status = document.get("status") or {}
    package_name = str(metadata.get("name", file_path.stem))
    default_channel = status.get("defaultChannel")

    channel_csv: str | None = None
    channels = status.get("channels") or []
    if default_channel and isinstance(channels, list):
        for ch in channels:
            if isinstance(ch, dict) and ch.get("name") == default_channel:
                channel_csv = ch.get("currentCSV")
                break

    return package_name, str(default_channel) if default_channel else "", channel_csv
