"""Leitura tolerante de YAML de inventário para diagramas."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_PLACEHOLDER = r"\[[A-Z][A-Z0-9_]*\]"
_PLACEHOLDER_KEY = re.compile(rf"(?m)^(\s*(?:-\s+)?)({_PLACEHOLDER})(:)")
_PLACEHOLDER_LIST_ITEM = re.compile(rf"(?m)^(\s+-\s+)({_PLACEHOLDER})(\s*)$")
_PLACEHOLDER_VALUE = re.compile(
    rf'(?m)^(\s*(?:-\s+)?[\w./-]+:[ \t]+)(?!["\'])([^\n]*{_PLACEHOLDER}[^\n]*)$'
)
_BROKEN_PROJECTED_TOKEN = re.compile(
    rf'(?m)^[ \t]*-[ \t]+"?{_PLACEHOLDER}"?[ \t]*:[ \t]*\d+[ \t]*\n(?:[ \t]+path:[ \t]*\S+[ \t]*\n)?'
)
_KIND_RE = re.compile(r"(?m)^kind:\s*(\S+)")
_NAME_RE = re.compile(r"(?m)^  name:\s*[\"']?([^\"'\s]+)[\"']?")
_NAMESPACE_RE = re.compile(r"(?m)^  namespace:\s*[\"']?([^\"'\s]+)[\"']?")
_LABELS_BLOCK_RE = re.compile(r"(?ms)^  labels:\n((?:    [^\n]+\n)+)")
_LABEL_LINE_RE = re.compile(
    r"^\s{4}([^:\s]+):\s*(?:\"([^\"]*)\"|'([^']*)'|(\S+))\s*$"
)
_OWNER_RE = re.compile(
    r"(?ms)^  ownerReferences:\n((?:  - .*\n(?:    .+\n)*)+)"
)
_OWNER_KIND_RE = re.compile(r"(?m)^\s+kind:\s*(\S+)")
_OWNER_NAME_RE = re.compile(r"(?m)^\s+name:\s*[\"']?([^\"'\s]+)[\"']?")
_API_VERSION_RE = re.compile(r"(?m)^apiVersion:\s*(\S+)")
_SA_RE = re.compile(r"(?m)^  serviceAccountName:\s*[\"']?([^\"'\s]+)[\"']?")
_CLAIM_RE = re.compile(r"(?m)^\s+claimName:\s*[\"']?([^\"'\s]+)[\"']?")


def sanitize_inventory_yaml(content: str) -> str:
    """Aspas em placeholders de sanitização (`[RG_REMOVIDO]`) para o YAML voltar a parsear."""
    quoted_keys = _PLACEHOLDER_KEY.sub(r'\1"\2"\3', content)
    quoted_items = _PLACEHOLDER_LIST_ITEM.sub(r'\1"\2"\3', quoted_keys)
    quoted_values = _PLACEHOLDER_VALUE.sub(
        lambda match: f'{match.group(1)}"{match.group(2).replace(chr(34), "")}"',
        quoted_items,
    )
    return _BROKEN_PROJECTED_TOKEN.sub("", quoted_values)


def _extract_labels(content: str) -> dict[str, str]:
    block = _LABELS_BLOCK_RE.search(content)
    if block is None:
        return {}
    labels: dict[str, str] = {}
    for line in block.group(1).splitlines():
        match = _LABEL_LINE_RE.match(line)
        if match is None:
            continue
        labels[match.group(1)] = match.group(2) or match.group(3) or match.group(4)
    return labels


def _extract_owners(content: str) -> list[dict[str, object]]:
    block = _OWNER_RE.search(content)
    if block is None:
        return []
    owners: list[dict[str, object]] = []
    for chunk in re.split(r"(?m)^  - ", block.group(1)):
        if not chunk.strip():
            continue
        kind_match = _OWNER_KIND_RE.search(chunk)
        name_match = _OWNER_NAME_RE.search(chunk)
        if kind_match is None or name_match is None:
            continue
        owners.append(
            {
                "kind": kind_match.group(1),
                "name": name_match.group(1),
                "controller": True,
            }
        )
    return owners


def stub_document_from_inventory(content: str, path: Path) -> dict | None:
    """Monta um documento mínimo a partir de campos visíveis no arquivo do inventário."""
    kind_match = _KIND_RE.search(content)
    name_match = _NAME_RE.search(content)
    kind = kind_match.group(1) if kind_match else None
    name = name_match.group(1) if name_match else path.stem
    if not kind:
        return None
    api_match = _API_VERSION_RE.search(content)
    namespace_match = _NAMESPACE_RE.search(content)
    metadata: dict[str, object] = {"name": name}
    if namespace_match:
        metadata["namespace"] = namespace_match.group(1)
    labels = _extract_labels(content)
    if labels:
        metadata["labels"] = labels
    owners = _extract_owners(content)
    if owners:
        metadata["ownerReferences"] = owners
    spec: dict[str, object] = {}
    sa_match = _SA_RE.search(content)
    if sa_match:
        spec["serviceAccountName"] = sa_match.group(1)
    claims = _CLAIM_RE.findall(content)
    if claims:
        spec["volumes"] = [
            {"name": claim, "persistentVolumeClaim": {"claimName": claim}}
            for claim in dict.fromkeys(claims)
        ]
    document: dict[str, object] = {
        "apiVersion": api_match.group(1) if api_match else "v1",
        "kind": kind,
        "metadata": metadata,
    }
    if spec:
        document["spec"] = spec
    return document


def load_diagram_documents(path: Path) -> list[dict]:
    """Carrega YAML do inventário, sanitizando placeholders quando necessário."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for candidate in (content, sanitize_inventory_yaml(content)):
        try:
            documents = list(yaml.safe_load_all(candidate))
        except yaml.YAMLError:
            continue
        loaded = [item for item in documents if isinstance(item, dict) and item.get("kind")]
        if loaded:
            return loaded
    stub = stub_document_from_inventory(content, path)
    return [stub] if stub else []
