"""Renderização de diagramas de arquitetura via KubeDiagrams."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import yaml

from kubeoptix_core_ai.normalize.ownership import infer_deployment_from_replicaset_name
from kubeoptix_core_ai.visualization.kubediagrams.config import bundled_config_path
from kubeoptix_core_ai.visualization.kubediagrams.yamlutil import load_diagram_documents
from kubeoptix_core_ai.visualization.png.assets import safe_asset_filename
from kubeoptix_core_ai.visualization.png.export_config import REPORT_IMAGE_DPI
from kubeoptix_core_ai.visualization.png.postprocess import finalize_report_png

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 180
KUBEDIAGRAMS_IMAGE = "docker.io/philippemerle/kubediagrams:latest"
_ENV_ENRICH_LABELS = "KUBEOPTIX_DIAGRAM_ENRICH_LABELS"
_EXTERNAL_NAMESPACE = "external"
_CLUSTERING_LABEL_KEYS = (
    "app.kubernetes.io/instance",
    "app.kubernetes.io/name",
    "app.kubernetes.io/component",
    "app.kubernetes.io/tier",
    "app.kubernetes.io/part-of",
    "app",
    "component",
    "tier",
    "release",
    "helm.sh/chart",
    "chart",
    "kubeoptix.io/domain",
)
_POD_DEPLOYMENT_PATTERN = re.compile(r"^(.+)-[a-f0-9]{8,10}-[a-z0-9]{5}$")
_POD_REPLICASET_PATTERN = re.compile(r"^(.+)-[a-f0-9]{8,10}$")
_POD_STATEFULSET_PATTERN = re.compile(r"^(.+)-\d+$")
_JOB_TIMESTAMP_PATTERN = re.compile(r"^(.+)-[0-9]{8,12}$")
_CANONICAL_CONTROLLER_KINDS = frozenset(
    {
        "Deployment",
        "StatefulSet",
        "DaemonSet",
        "DeploymentConfig",
        "Job",
        "CronJob",
        "ReplicationController",
        "ReplicaSet",
    }
)
_CATEGORY_LABEL_WORKLOADS = "kubeoptix.io/cat-workloads"
_CATEGORY_LABEL_PODS = "kubeoptix.io/cat-pods"
_CATEGORY_LABEL_NETWORKING = "kubeoptix.io/cat-networking"
_CATEGORY_LABEL_STORAGE = "kubeoptix.io/cat-storage"
_CATEGORY_LABEL_CONFIG = "kubeoptix.io/cat-config"
_KIND_CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "Deployment": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "StatefulSet": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "DaemonSet": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "DeploymentConfig": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "ReplicaSet": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "ReplicationController": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "Job": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "CronJob": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "HorizontalPodAutoscaler": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "VerticalPodAutoscaler": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "PodDisruptionBudget": {_CATEGORY_LABEL_WORKLOADS: "Workloads"},
    "Pod": {
        _CATEGORY_LABEL_WORKLOADS: "Workloads",
        _CATEGORY_LABEL_PODS: "Pods",
    },
    "Service": {_CATEGORY_LABEL_NETWORKING: "Networking"},
    "Route": {_CATEGORY_LABEL_NETWORKING: "Networking"},
    "Ingress": {_CATEGORY_LABEL_NETWORKING: "Networking"},
    "NetworkPolicy": {_CATEGORY_LABEL_NETWORKING: "Networking"},
    "PersistentVolume": {_CATEGORY_LABEL_STORAGE: "Storage"},
    "PersistentVolumeClaim": {_CATEGORY_LABEL_STORAGE: "Storage"},
    "StorageClass": {_CATEGORY_LABEL_STORAGE: "Storage"},
    "ConfigMap": {_CATEGORY_LABEL_CONFIG: "Configuration"},
    "Secret": {_CATEGORY_LABEL_CONFIG: "Configuration"},
    "ServiceAccount": {_CATEGORY_LABEL_CONFIG: "Configuration"},
}


def find_container_runtime() -> str | None:
    """Retorna ``podman`` ou ``docker`` se disponível no PATH."""
    for runtime in ("podman", "docker"):
        if shutil.which(runtime) is not None:
            return runtime
    return None


def is_kubediagrams_available() -> bool:
    """Verifica se KubeDiagrams pode ser executado (local ou via container)."""
    if shutil.which("kube-diagrams") is not None and shutil.which("dot") is not None:
        return True
    return find_container_runtime() is not None


def find_kube_diagrams_executable() -> str | None:
    return shutil.which("kube-diagrams")


_DOT_NODE_ID_RE = re.compile(
    r'(?m)^\s+("[0-9a-fA-F]{32}"|[A-Fa-f][0-9a-fA-F]{31})\s*\['
)
_DOT_EDGE_RE = re.compile(
    r'(?m)^(\t(?:\"[0-9a-fA-F]{32}\"|[A-Fa-f][0-9a-fA-F]{31}) -> '
    r'(?:\"[0-9a-fA-F]{32}\"|[A-Fa-f][0-9a-fA-F]{31}) \[)([^\]]*)(\])'
)
_LEFT_COLUMN_CLUSTERS = ("Workloads", "Configuration", "Storage")
_HORIZONTAL_CLUSTER_ORDER = (*_LEFT_COLUMN_CLUSTERS, "Networking")
_CATEGORY_CLUSTER_NAMES = _HORIZONTAL_CLUSTER_ORDER


def _extract_dot_subgraph(source: str, marker: str) -> tuple[str, int, int] | None:
    start = source.find(marker)
    if start < 0:
        return None
    brace = source.find("{", start)
    if brace < 0:
        return None
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1], start, index + 1
    return None


def _dot_node_ids(cluster_src: str) -> list[str]:
    return _DOT_NODE_ID_RE.findall(cluster_src)


def _force_horizontal_rankdir(dot_source: str) -> str:
    """Força fluxo esquerda→direita no grafo raiz e no cluster do namespace."""
    tuned = dot_source.replace("rankdir=TB", "rankdir=LR")
    if 'rankdir=LR' not in tuned.split("subgraph", 1)[0]:
        tuned = re.sub(
            r"(?m)^(\tgraph \[)([^\]]*)(\])",
            lambda match: (
                match.group(1)
                + match.group(2)
                + (" rankdir=LR" if "rankdir=" not in match.group(2) else "")
                + match.group(3)
            ),
            tuned,
            count=1,
        )
    tuned = re.sub(
        r'(subgraph "cluster_Namespace:[^"]*" \{\s*graph \[[^\]]*?)rankdir=[A-Z]{2}',
        r"\1rankdir=LR",
        tuned,
        count=1,
        flags=re.DOTALL,
    )
    return tuned


def _ensure_root_layout_attrs(dot_source: str) -> str:
    match = re.search(r"(?m)^(\tgraph \[)([^\]]*)(\])", dot_source)
    if match is None:
        return dot_source
    body = match.group(2)
    additions: list[str] = []
    if "compound=" not in body:
        additions.append("compound=true")
    if "newrank=" not in body:
        additions.append("newrank=true")
    if "rankdir=" not in body:
        additions.append("rankdir=LR")
    if "margin=" not in body:
        additions.append("margin=0")
    if "pad=" not in body:
        additions.append("pad=0.05")
    if "dpi=" not in body:
        additions.append(f"dpi={REPORT_IMAGE_DPI}")
    if not additions:
        return dot_source
    return (
        dot_source[: match.start(2)]
        + body
        + " "
        + " ".join(additions)
        + dot_source[match.end(2) :]
    )


def _relax_inter_cluster_edges(dot_source: str, membership: dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        edge_ids = re.findall(
            r'"[0-9a-fA-F]{32}"|[A-Fa-f][0-9a-fA-F]{31}', match.group(1)
        )
        if len(edge_ids) < 2:
            return match.group(0)
        source_cluster = membership.get(edge_ids[0])
        target_cluster = membership.get(edge_ids[1])
        if not source_cluster or not target_cluster or source_cluster == target_cluster:
            return match.group(0)
        attrs = match.group(2)
        if "constraint=" not in attrs:
            attrs += " constraint=false"
        return match.group(1) + attrs + match.group(3)

    return _DOT_EDGE_RE.sub(_replace, dot_source)


def _sequence_category_clusters_horizontally(dot_source: str) -> str:
    """Reordena agrupamentos para leitura horizontal: Workloads → … → Networking."""
    found: dict[str, tuple[str, int, int]] = {}
    for name in _HORIZONTAL_CLUSTER_ORDER:
        extracted = _extract_dot_subgraph(dot_source, f"subgraph cluster_{name} {{")
        if extracted is not None:
            found[name] = extracted
    if len(found) < 2:
        return dot_source
    first = min(item[1] for item in found.values())
    last = max(item[2] for item in found.values())
    ordered_parts = [
        found[name][0].replace(" rank=min", "").replace("rank=min ", "")
        for name in _HORIZONTAL_CLUSTER_ORDER
        if name in found
    ]
    if not ordered_parts:
        return dot_source
    return dot_source[:first] + "\n".join(ordered_parts) + "\n" + dot_source[last:]


def _layout_rank_constraints(dot_source: str) -> str:
    workloads = _extract_dot_subgraph(dot_source, "subgraph cluster_Workloads {")
    if workloads is None:
        return dot_source
    pods = _extract_dot_subgraph(workloads[0], "subgraph cluster_Pods {")
    pod_nodes = _dot_node_ids(pods[0]) if pods is not None else []
    workload_nodes = _dot_node_ids(workloads[0])
    controller_nodes = [node for node in workload_nodes if node not in set(pod_nodes)]
    config = _extract_dot_subgraph(dot_source, "subgraph cluster_Configuration {")
    storage = _extract_dot_subgraph(dot_source, "subgraph cluster_Storage {")
    networking = _extract_dot_subgraph(dot_source, "subgraph cluster_Networking {")
    config_nodes = _dot_node_ids(config[0]) if config is not None else []
    storage_nodes = _dot_node_ids(storage[0]) if storage is not None else []
    network_nodes = _dot_node_ids(networking[0]) if networking is not None else []

    lines: list[str] = []
    if len(pod_nodes) > 1:
        lines.append(f"\t{{ rank=same; {'; '.join(pod_nodes)}; }}")
    if config_nodes:
        lines.append(f"\t{{ rank=same; {'; '.join(config_nodes)}; }}")
    if storage_nodes:
        lines.append(f"\t{{ rank=same; {'; '.join(storage_nodes)}; }}")

    workload_anchor = (
        controller_nodes[0]
        if controller_nodes
        else (pod_nodes[0] if pod_nodes else None)
    )
    anchors: list[str] = []
    for node in (
        workload_anchor,
        config_nodes[0] if config_nodes else None,
        storage_nodes[0] if storage_nodes else None,
        network_nodes[0] if network_nodes else None,
    ):
        if node and (not anchors or anchors[-1] != node):
            anchors.append(node)

    for source_id, target_id in zip(anchors, anchors[1:], strict=False):
        lines.append(
            f"\t{source_id} -> {target_id} [style=invis weight=200 minlen=2];"
        )

    if not lines:
        return dot_source
    closing = dot_source.rfind("}")
    if closing < 0:
        return dot_source
    return dot_source[:closing] + "\n" + "\n".join(lines) + "\n" + dot_source[closing:]


class KubeDiagramsRenderer:
    """Gera PNGs de arquitetura a partir de manifests YAML via KubeDiagrams."""

    def __init__(
        self,
        assets_dir: Path,
        *,
        namespace: str,
        path_prefix: str = "",
        config_path: Path | None = None,
    ) -> None:
        self._assets_dir = assets_dir
        self._namespace = namespace
        self._path_prefix = path_prefix.strip("/")
        self._config_path = config_path if config_path is not None else bundled_config_path()
        self._assets_dir.mkdir(parents=True, exist_ok=True)
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _set_error(self, message: str | None) -> None:
        self._last_error = message

    def _relative_path(self, viz_id: str) -> str:
        filename = safe_asset_filename(viz_id)
        if self._path_prefix:
            return f"{self._path_prefix}/{filename}"
        return filename

    def _output_path(self, viz_id: str) -> Path:
        return self._assets_dir / safe_asset_filename(viz_id)

    def render_namespace_architecture(
        self,
        namespace_root: Path,
        *,
        viz_id: str = "namespace_architecture",
    ) -> str | None:
        """Gera diagrama PNG do namespace (atalho para manifests de arquitetura)."""
        from kubeoptix_core_ai.visualization.kubediagrams.manifests import (
            select_architecture_manifests,
        )

        manifests = select_architecture_manifests(namespace_root)
        if not manifests:
            return None
        return self.render_manifests(viz_id, manifests)

    def render_manifests(self, viz_id: str, manifests: tuple[Path, ...]) -> str | None:
        """
        Gera PNG a partir de uma lista de manifests YAML.

        Retorna caminho relativo para o Markdown ou ``None`` se indisponível/falhar.
        """
        self._set_error(None)
        if not is_kubediagrams_available():
            logger.debug("KubeDiagrams indisponível (sem CLI/dot nem container runtime)")
            self._set_error("kube-diagrams/dot indisponível no PATH e sem runtime de container")
            return None
        if not manifests:
            logger.debug("Nenhum manifest fornecido para %s", viz_id)
            self._set_error("nenhum manifest YAML fornecido para renderização")
            return None
        valid_manifests = self._filter_parseable_manifests(manifests)
        if not valid_manifests:
            self._set_error("nenhum manifest YAML válido/parseável para renderização")
            return None

        render_manifests, temporary_dir = self._build_enriched_manifest_set(
            valid_manifests,
            enrich=self._env_flag(_ENV_ENRICH_LABELS, default=True),
        )

        output_path = self._output_path(viz_id)
        try:
            if not self._invoke_kube_diagrams(render_manifests, output_path):
                if self._is_yaml_parse_error(self._last_error) and len(render_manifests) > 1:
                    filtered = self._filter_manifests_by_kubediagrams_parse(render_manifests)
                    if filtered and len(filtered) < len(render_manifests):
                        logger.warning(
                            "KubeDiagrams: reprocessando %s com %d/%d manifests após excluir YAMLs inválidos para o parser do kube-diagrams",
                            viz_id,
                            len(filtered),
                            len(render_manifests),
                        )
                        self._set_error(None)
                        if self._invoke_kube_diagrams(filtered, output_path):
                            return self._relative_path(viz_id)
                if self._last_error is None:
                    self._set_error("falha não detalhada ao executar KubeDiagrams")
                return None
            return self._relative_path(viz_id)
        finally:
            if temporary_dir is not None:
                temporary_dir.cleanup()

    def _is_yaml_parse_error(self, error: str | None) -> bool:
        if not error:
            return False
        markers = (
            "yaml.safe_load_all",
            "yaml.parser.ParserError",
            "yaml.scanner.ScannerError",
            "construct_document",
        )
        return any(marker in error for marker in markers)

    def _env_flag(self, name: str, default: bool = False) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _strip_clustering_labels(self, labels: dict) -> None:
        for key in _CLUSTERING_LABEL_KEYS:
            labels.pop(key, None)

    def _is_external_service(self, document: dict) -> bool:
        if document.get("kind") != "Service":
            return False
        spec = document.get("spec")
        if not isinstance(spec, dict):
            return False
        if spec.get("type") == "ExternalName" and spec.get("externalName"):
            return True
        return False

    def _external_peer_manifest(self, service: dict) -> dict:
        spec = service.get("spec") if isinstance(service.get("spec"), dict) else {}
        external_name = str(spec.get("externalName") or "external")
        metadata = service.get("metadata") if isinstance(service.get("metadata"), dict) else {}
        service_name = str(metadata.get("name") or external_name)
        peer_name = re.sub(r"[^a-zA-Z0-9-]+", "-", external_name).strip("-").lower()[:63] or "peer"
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": peer_name,
                "namespace": _EXTERNAL_NAMESPACE,
                "labels": {
                    "kubeoptix.io/external-peer": service_name,
                    _CATEGORY_LABEL_NETWORKING: "Networking",
                },
            },
            "spec": {
                "type": "ExternalName",
                "externalName": external_name,
            },
        }

    def _collect_external_peer_manifests(self, manifests: tuple[Path, ...]) -> list[dict]:
        peers: list[dict] = []
        seen: set[str] = set()
        for source in manifests:
            docs = load_diagram_documents(source)
            for document in docs:
                if not isinstance(document, dict) or not self._is_external_service(document):
                    continue
                peer = self._external_peer_manifest(document)
                peer_name = peer["metadata"]["name"]
                if peer_name in seen:
                    continue
                seen.add(peer_name)
                peers.append(peer)
        return peers

    def _normalize_manifest_document(self, document: dict) -> bool:
        if not isinstance(document, dict):
            return False
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            document["metadata"] = metadata
        labels = metadata.get("labels")
        if not isinstance(labels, dict):
            labels = {}
            metadata["labels"] = labels

        changed = False
        if metadata.get("namespace") in (None, ""):
            metadata["namespace"] = self._namespace
            changed = True

        before = set(labels)
        self._strip_clustering_labels(labels)
        if set(labels) != before:
            changed = True
        if self._apply_category_labels(document):
            changed = True
        return changed

    def _apply_category_labels(self, document: dict) -> bool:
        kind = str(document.get("kind") or "")
        category_labels = _KIND_CATEGORY_LABELS.get(kind)
        if not category_labels:
            return False
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            document["metadata"] = metadata
        labels = metadata.get("labels")
        if not isinstance(labels, dict):
            labels = {}
            metadata["labels"] = labels
        changed = False
        for key, value in category_labels.items():
            if labels.get(key) != value:
                labels[key] = value
                changed = True
        return changed

    def _replica_label(self, name: str, count: int) -> str:
        unit = "replica" if count == 1 else "replicas"
        return f"{name} ({count} {unit})"

    def _service_port_suffix(self, document: dict) -> str:
        spec = document.get("spec")
        if not isinstance(spec, dict):
            return ""
        ports = spec.get("ports")
        if not isinstance(ports, list):
            return ""
        numbers: list[str] = []
        for item in ports:
            if not isinstance(item, dict) or item.get("port") is None:
                continue
            numbers.append(str(item["port"]))
        if not numbers:
            return ""
        return ":" + ",".join(numbers)

    def _apply_service_port_display(self, document: dict) -> tuple[str, str] | None:
        if document.get("kind") != "Service":
            return None
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            return None
        original = str(metadata.get("name") or "").strip()
        if not original:
            return None
        suffix = self._service_port_suffix(document)
        if not suffix or original.endswith(suffix):
            return None
        annotations = metadata.get("annotations")
        if not isinstance(annotations, dict):
            annotations = {}
            metadata["annotations"] = annotations
        annotations.setdefault("kubeoptix.io/original-name", original)
        metadata["name"] = f"{original}{suffix}"
        return original, str(metadata["name"])

    def _patch_service_name_refs(
        self,
        document: dict,
        renames: dict[tuple[str, str], str],
    ) -> None:
        if not renames:
            return
        metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
        namespace = str(metadata.get("namespace") or self._namespace)
        kind = str(document.get("kind") or "")
        spec = document.get("spec")
        if not isinstance(spec, dict):
            return

        def _rename(name: object) -> str | None:
            if not isinstance(name, str) or not name:
                return None
            return renames.get((namespace, name)) or renames.get((self._namespace, name))

        if kind == "Route":
            target = spec.get("to")
            if isinstance(target, dict):
                replacement = _rename(target.get("name"))
                if replacement:
                    target["name"] = replacement
            backends = spec.get("alternateBackends")
            if isinstance(backends, list):
                for backend in backends:
                    if not isinstance(backend, dict):
                        continue
                    replacement = _rename(backend.get("name"))
                    if replacement:
                        backend["name"] = replacement
            return
        if kind == "Ingress":
            default_backend = spec.get("defaultBackend")
            if isinstance(default_backend, dict):
                service = default_backend.get("service")
                if isinstance(service, dict):
                    replacement = _rename(service.get("name"))
                    if replacement:
                        service["name"] = replacement
            rules = spec.get("rules")
            if isinstance(rules, list):
                for rule in rules:
                    if not isinstance(rule, dict):
                        continue
                    http = rule.get("http")
                    if not isinstance(http, dict):
                        continue
                    paths = http.get("paths")
                    if not isinstance(paths, list):
                        continue
                    for path_item in paths:
                        if not isinstance(path_item, dict):
                            continue
                        backend = path_item.get("backend")
                        if not isinstance(backend, dict):
                            continue
                        service = backend.get("service")
                        if isinstance(service, dict):
                            replacement = _rename(service.get("name"))
                            if replacement:
                                service["name"] = replacement
            return
        if kind == "StatefulSet":
            replacement = _rename(spec.get("serviceName"))
            if replacement:
                spec["serviceName"] = replacement

    def _enrich_manifest_documents(self, documents: list[dict]) -> bool:
        changed = False
        for document in documents:
            if not isinstance(document, dict):
                continue
            if self._normalize_manifest_document(document):
                changed = True
        return changed

    def _source_is_native_parseable(self, path: Path) -> bool:
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError):
            return False
        return bool(documents) and not all(item is None for item in documents)

    def _pod_group_key(self, pod_name: str) -> str:
        """
        Calcula a chave de agrupamento de Pods equivalentes.

        Exemplos:
        - deployment-rs pods: app-7f98c8d4c9-abcde -> app
        - replicaset: app-7f98c8d4c9 -> app
        - statefulset: app-0 -> app
        """
        if match := _POD_DEPLOYMENT_PATTERN.match(pod_name):
            return match.group(1)
        if match := _POD_REPLICASET_PATTERN.match(pod_name):
            return match.group(1)
        if match := _POD_STATEFULSET_PATTERN.match(pod_name):
            return match.group(1)
        return pod_name

    def _controller_group_from_owner_refs(self, document: dict) -> str | None:
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            return None
        owners = metadata.get("ownerReferences")
        if not isinstance(owners, list):
            return None
        for owner in owners:
            if not isinstance(owner, dict):
                continue
            if owner.get("controller") is False:
                continue
            kind = str(owner.get("kind") or "")
            name = str(owner.get("name") or "")
            if not name or kind not in _CANONICAL_CONTROLLER_KINDS:
                continue
            if kind == "ReplicaSet":
                return infer_deployment_from_replicaset_name(name) or name
            return name
        return None

    def _job_group_key(self, job_name: str) -> str:
        if match := _JOB_TIMESTAMP_PATTERN.match(job_name):
            return match.group(1)
        return job_name

    def _collect_kind_grouping(
        self,
        manifests: tuple[Path, ...],
        *,
        kind: str,
        path_marker: str,
        fallback_key: Callable[[str], str],
    ) -> tuple[dict[Path, tuple[str, int]], set[Path], set[Path]]:
        counts: dict[str, int] = {}
        representative: dict[str, Path] = {}
        seen: set[Path] = set()

        for source in manifests:
            if path_marker not in str(source).lower():
                continue
            docs = load_diagram_documents(source)
            document = next(
                (item for item in docs if isinstance(item, dict) and item.get("kind") == kind),
                None,
            )
            if not isinstance(document, dict):
                continue
            metadata = document.get("metadata")
            if not isinstance(metadata, dict):
                continue
            resource_name = str(metadata.get("name") or source.stem)
            group_key = self._controller_group_from_owner_refs(document) or fallback_key(
                resource_name
            )
            counts[group_key] = counts.get(group_key, 0) + 1
            representative.setdefault(group_key, source)
            seen.add(source)

        representative_set = set(representative.values())
        info_by_path = {
            path: (group_key, counts[group_key])
            for group_key, path in representative.items()
        }
        return info_by_path, representative_set, seen

    def _collect_pod_grouping(
        self, manifests: tuple[Path, ...]
    ) -> tuple[dict[Path, tuple[str, int]], set[Path], set[Path]]:
        return self._collect_kind_grouping(
            manifests,
            kind="Pod",
            path_marker="/pods/",
            fallback_key=self._pod_group_key,
        )

    def _collect_job_grouping(
        self, manifests: tuple[Path, ...]
    ) -> tuple[dict[Path, tuple[str, int]], set[Path], set[Path]]:
        return self._collect_kind_grouping(
            manifests,
            kind="Job",
            path_marker="/jobs",
            fallback_key=self._job_group_key,
        )

    def _apply_group_display(
        self,
        document: dict,
        *,
        expected_kind: str,
        group_key: str,
        count: int,
        source_stem: str,
    ) -> None:
        if document.get("kind") != expected_kind:
            return
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            document["metadata"] = metadata
        labels = metadata.get("labels")
        if not isinstance(labels, dict):
            labels = {}
            metadata["labels"] = labels
        annotations = metadata.get("annotations")
        if not isinstance(annotations, dict):
            annotations = {}
            metadata["annotations"] = annotations
        original_name = str(metadata.get("name") or source_stem)
        annotations.setdefault("kubeoptix.io/original-name", original_name)
        size_key = "kubeoptix.io/pod-group-size" if expected_kind == "Pod" else "kubeoptix.io/job-group-size"
        group_label_key = "kubeoptix.io/pod-group" if expected_kind == "Pod" else "kubeoptix.io/job-group"
        labels[size_key] = str(count)
        labels[group_label_key] = group_key
        metadata["name"] = self._replica_label(group_key, count)

    def _apply_group_display_to_documents(
        self,
        documents: list[dict],
        source: Path,
        grouping: dict[Path, tuple[str, int]],
        expected_kind: str,
    ) -> bool:
        if source not in grouping:
            return False
        group_key, count = grouping[source]
        patched = False
        for document in documents:
            if not isinstance(document, dict) or document.get("kind") != expected_kind:
                continue
            self._apply_group_display(
                document,
                expected_kind=expected_kind,
                group_key=group_key,
                count=count,
                source_stem=source.stem,
            )
            patched = True
        return patched

    def _write_documents(self, target: Path, documents: list[dict]) -> None:
        target.write_text(
            yaml.safe_dump_all(documents, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )

    def _build_enriched_manifest_set(
        self,
        manifests: tuple[Path, ...],
        *,
        enrich: bool = True,
    ) -> tuple[tuple[Path, ...], tempfile.TemporaryDirectory[str] | None]:
        loaded: list[tuple[Path, list[dict]]] = []
        for source in manifests:
            documents = load_diagram_documents(source)
            if documents:
                loaded.append((source, documents))
        if not loaded:
            return (), None

        if not enrich:
            native_ok = all(self._source_is_native_parseable(source) for source, _ in loaded)
            if native_ok:
                return tuple(source for source, _ in loaded), None
            temp_dir = tempfile.TemporaryDirectory(prefix="kd_sanitized_")
            output_root = Path(temp_dir.name)
            paths: list[Path] = []
            for idx, (source, documents) in enumerate(loaded):
                if self._source_is_native_parseable(source):
                    paths.append(source)
                    continue
                target = output_root / f"{idx:04d}_{source.name}"
                self._write_documents(target, documents)
                paths.append(target)
            return tuple(paths), temp_dir

        temp_dir = tempfile.TemporaryDirectory(prefix="kd_enriched_")
        output_root = Path(temp_dir.name)
        enriched_paths: list[Path] = []
        source_paths = tuple(source for source, _ in loaded)
        pod_info_by_path, pod_representatives, seen_pods = self._collect_pod_grouping(
            source_paths
        )
        job_info_by_path, job_representatives, seen_jobs = self._collect_job_grouping(
            source_paths
        )
        service_renames: dict[tuple[str, str], str] = {}
        prepared: list[tuple[Path, list[dict]]] = []

        for source, documents in loaded:
            if source in seen_pods and source not in pod_representatives:
                continue
            if source in seen_jobs and source not in job_representatives:
                continue
            self._enrich_manifest_documents(documents)
            self._apply_group_display_to_documents(
                documents, source, pod_info_by_path, "Pod"
            )
            self._apply_group_display_to_documents(
                documents, source, job_info_by_path, "Job"
            )
            for document in documents:
                if not isinstance(document, dict):
                    continue
                renamed = self._apply_service_port_display(document)
                if renamed is None:
                    continue
                original, display = renamed
                metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
                namespace = str(metadata.get("namespace") or self._namespace)
                service_renames[(namespace, original)] = display
            prepared.append((source, documents))

        external_peers = self._collect_external_peer_manifests(
            tuple(source for source, _ in prepared)
        )

        for source, documents in prepared:
            for document in documents:
                if isinstance(document, dict):
                    self._patch_service_name_refs(document, service_renames)
            target = output_root / f"{len(enriched_paths):04d}_{source.name}"
            self._write_documents(target, documents)
            enriched_paths.append(target)

        for peer_idx, peer in enumerate(external_peers):
            target = output_root / f"ext_{peer_idx:04d}_{peer['metadata']['name']}.yaml"
            target.write_text(
                yaml.safe_dump(peer, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
            enriched_paths.append(target)

        if not enriched_paths:
            temp_dir.cleanup()
            return manifests, None
        return tuple(enriched_paths), temp_dir

    def _filter_parseable_manifests(self, manifests: tuple[Path, ...]) -> tuple[Path, ...]:
        valid: list[Path] = []
        for path in manifests:
            documents = load_diagram_documents(path)
            if not documents:
                logger.warning("Manifest ignorado (YAML inválido ou vazio): %s", path)
                continue
            valid.append(path)
        if len(valid) < len(manifests):
            logger.info(
                "KubeDiagrams: %d/%d manifests válidos após filtro YAML",
                len(valid),
                len(manifests),
            )
        return tuple(valid)

    def _filter_manifests_by_kubediagrams_parse(
        self, manifests: tuple[Path, ...]
    ) -> tuple[Path, ...]:
        """Filtra manifests que o parser interno do `kube-diagrams` rejeita."""
        executable = find_kube_diagrams_executable()
        if executable is None or shutil.which("dot") is None:
            return manifests

        valid: list[Path] = []
        for manifest in manifests:
            with tempfile.NamedTemporaryFile(
                prefix="kd_probe_",
                suffix=".png",
                dir=self._assets_dir,
                delete=False,
            ) as tmp:
                probe_output = Path(tmp.name)
            command = [
                executable,
                "-f",
                "png",
                "-o",
                str(probe_output),
                str(manifest),
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.warning(
                    "KubeDiagrams: erro ao validar manifest %s (%s); mantendo arquivo",
                    manifest,
                    exc,
                )
                valid.append(manifest)
                continue
            finally:
                try:
                    probe_output.unlink(missing_ok=True)
                except OSError:
                    pass

            if result.returncode == 0:
                valid.append(manifest)
            else:
                stderr = (result.stderr or "").strip()
                if self._is_yaml_parse_error(stderr):
                    logger.warning(
                        "KubeDiagrams: manifest removido por erro de parse YAML interno: %s",
                        manifest,
                    )
                else:
                    # Erros não relacionados ao parser YAML não devem remover o manifest.
                    valid.append(manifest)
        return tuple(valid)

    def _invoke_kube_diagrams(self, manifests: tuple[Path, ...], output_path: Path) -> bool:
        if find_kube_diagrams_executable() is not None:
            if self._invoke_local_kube_diagrams(manifests, output_path, use_config=True):
                return True
            if self._has_config_file():
                logger.warning(
                    "KubeDiagrams local falhou com configuração; tentando novamente sem -c"
                )
                if self._invoke_local_kube_diagrams(manifests, output_path, use_config=False):
                    return True
            logger.debug("KubeDiagrams local falhou; tentando container")

        runtime = find_container_runtime()
        if runtime is not None:
            if self._invoke_container_kube_diagrams(
                runtime, manifests, output_path, use_config=True
            ):
                return True
            if self._has_config_file():
                logger.warning(
                    "KubeDiagrams em container falhou com configuração; tentando novamente sem -c"
                )
                if self._invoke_container_kube_diagrams(
                    runtime, manifests, output_path, use_config=False
                ):
                    return True

        return False

    def _has_config_file(self) -> bool:
        return self._config_path is not None and self._config_path.is_file()

    def _config_args(self, *, container: bool) -> list[str]:
        if not self._has_config_file():
            return []
        if container:
            return ["-c", "/kdconfig/kube-diagrams.yml"]
        return ["-c", str(self._config_path)]

    def _tune_dot_layout(self, dot_source: str) -> str:
        """Organiza agrupamentos em fluxo horizontal (LR) para leitura humana."""
        tuned = _force_horizontal_rankdir(dot_source)
        membership: dict[str, str] = {}
        for name in _CATEGORY_CLUSTER_NAMES:
            extracted = _extract_dot_subgraph(tuned, f"subgraph cluster_{name} {{")
            if extracted is None:
                continue
            for node_id in _dot_node_ids(extracted[0]):
                membership[node_id] = name
        tuned = _sequence_category_clusters_horizontally(tuned)
        tuned = tuned.replace(" rank=min", "").replace("rank=min ", "")
        if membership:
            tuned = _relax_inter_cluster_edges(tuned, membership)
        tuned = _ensure_root_layout_attrs(tuned)
        return _layout_rank_constraints(tuned)

    def _read_generated_dot(self, requested: Path) -> str | None:
        stem = requested.with_suffix("")
        candidates = (requested, stem, stem.with_suffix(".dot"))
        seen: set[Path] = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "digraph" in text:
                return text
        return None

    def _dot_icon_volume_args(self, dot_source: str) -> list[str]:
        images = [
            Path(path)
            for path in re.findall(r'image="([^"]+)"', dot_source)
            if path.startswith("/")
        ]
        existing = [path for path in images if path.is_file()]
        if not existing:
            return []
        root = Path(os.path.commonpath([str(path) for path in existing]))
        if root.is_file():
            root = root.parent
        return ["-v", f"{root}:{root}:ro,Z"]

    def _render_dot_to_png_with_runtime(
        self, runtime: str, dot_source: str, output_path: Path
    ) -> bool:
        dot_name = f".kd_layout_{output_path.stem}.dot"
        host_dot = self._assets_dir / dot_name
        try:
            host_dot.write_text(dot_source, encoding="utf-8")
            command = [
                runtime,
                "run",
                "--rm",
                "-v",
                f"{self._assets_dir.resolve()}:/out:Z",
                *self._dot_icon_volume_args(dot_source),
                KUBEDIAGRAMS_IMAGE,
                "dot",
                "-Tpng",
                "-o",
                f"/out/{output_path.name}",
                f"/out/{dot_name}",
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Falha ao renderizar DOT via container: %s", exc)
            return False
        finally:
            try:
                host_dot.unlink(missing_ok=True)
            except OSError:
                pass
        if not (output_path.is_file() and output_path.stat().st_size > 0):
            logger.warning(
                "dot em container não produziu PNG (exit %s): %s",
                getattr(result, "returncode", "?"),
                (getattr(result, "stderr", None) or "")[:1000],
            )
            return False
        finalize_report_png(output_path, profile="diagram")
        return True

    def _render_dot_to_png(self, dot_source: str, output_path: Path) -> bool:
        if shutil.which("dot") is not None:
            with tempfile.NamedTemporaryFile(
                prefix="kd_layout_",
                suffix=".dot",
                dir=self._assets_dir,
                delete=False,
            ) as tmp:
                dot_path = Path(tmp.name)
            try:
                dot_path.write_text(dot_source, encoding="utf-8")
                result = subprocess.run(
                    [shutil.which("dot"), "-Tpng", "-o", str(output_path), str(dot_path)],
                    capture_output=True,
                    text=True,
                    timeout=_DEFAULT_TIMEOUT_SECONDS,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.warning("Falha ao renderizar DOT: %s", exc)
                result = None
            finally:
                try:
                    dot_path.unlink(missing_ok=True)
                except OSError:
                    pass
            if result is not None and result.returncode == 0:
                if output_path.is_file() and output_path.stat().st_size > 0:
                    finalize_report_png(output_path, profile="diagram")
                    return True
        runtime = find_container_runtime()
        if runtime is not None:
            return self._render_dot_to_png_with_runtime(runtime, dot_source, output_path)
        return False

    def _invoke_local_kube_diagrams_dot(
        self,
        manifests: tuple[Path, ...],
        output_path: Path,
        *,
        use_config: bool,
    ) -> bool:
        executable = find_kube_diagrams_executable()
        if executable is None:
            return False
        with tempfile.NamedTemporaryFile(
            prefix="kd_dot_",
            suffix=".dot",
            dir=self._assets_dir,
            delete=False,
        ) as tmp:
            dot_output = Path(tmp.name)
        extras = [dot_output, dot_output.with_suffix("")]
        try:
            command: list[str] = [
                executable,
                "-f",
                "dot",
                "-o",
                str(dot_output),
                *(self._config_args(container=False) if use_config else []),
                *(str(path) for path in manifests),
            ]
            subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
                check=False,
            )
            source = self._read_generated_dot(dot_output)
            if not source:
                return False
            tuned = self._tune_dot_layout(source)
            return self._render_dot_to_png(tuned, output_path)
        except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
            return False
        finally:
            for path in extras:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _invoke_local_kube_diagrams(
        self,
        manifests: tuple[Path, ...],
        output_path: Path,
        *,
        use_config: bool,
    ) -> bool:
        executable = find_kube_diagrams_executable()
        if executable is None:
            return False

        if self._invoke_local_kube_diagrams_dot(
            manifests, output_path, use_config=use_config
        ):
            return True
        if shutil.which("dot") is None:
            return False

        command: list[str] = [
            executable,
            "-f",
            "png",
            "-o",
            str(output_path),
            *(
                self._config_args(container=False)
                if use_config
                else []
            ),
            *(str(path) for path in manifests),
        ]
        return self._run_command(command, output_path=output_path)

    def _invoke_container_kube_diagrams(
        self,
        runtime: str,
        manifests: tuple[Path, ...],
        output_path: Path,
        *,
        use_config: bool,
    ) -> bool:
        resolved = [path.resolve() for path in manifests]
        work_root = Path(os.path.commonpath([str(path) for path in resolved]))
        if work_root.is_file():
            work_root = work_root.parent

        container_manifests = [
            f"/work/{path.relative_to(work_root).as_posix()}" for path in resolved
        ]
        container_output = f"/out/{output_path.name}"

        volumes = [
            "-v",
            f"{work_root}:/work:ro,Z",
            "-v",
            f"{self._assets_dir.resolve()}:/out:Z",
        ]
        if use_config and self._has_config_file():
            config_dir = self._config_path.resolve().parent
            volumes.extend(["-v", f"{config_dir}:/kdconfig:ro,Z"])

        command: list[str] = [
            runtime,
            "run",
            "--rm",
            *volumes,
            KUBEDIAGRAMS_IMAGE,
            "kube-diagrams",
            "-f",
            "png",
            "-o",
            container_output,
            *(
                self._config_args(container=True)
                if use_config
                else []
            ),
            *container_manifests,
        ]
        logger.debug(
            "Executando KubeDiagrams via %s (%d manifests)",
            runtime,
            len(container_manifests),
        )
        return self._run_command(command, output_path=output_path)

    def _run_command(self, command: list[str], *, output_path: Path) -> bool:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Falha ao executar KubeDiagrams: %s", exc)
            self._set_error(f"erro de execução: {exc}")
            return False

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            logger.warning(
                "KubeDiagrams retornou código %s: %s",
                result.returncode,
                stderr[:2000] if stderr else "(sem stderr)",
            )
            self._set_error(
                f"exit_code={result.returncode}; stderr={(stderr[:2000] if stderr else '(sem stderr)')}"
            )
            return False

        if not output_path.is_file() or output_path.stat().st_size <= 0:
            logger.warning("KubeDiagrams não produziu arquivo PNG: %s", output_path)
            self._set_error(f"arquivo PNG não produzido ou vazio: {output_path}")
            return False

        finalize_report_png(output_path, profile="diagram")
        return True
