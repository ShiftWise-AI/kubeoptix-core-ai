"""Renderização de diagramas de arquitetura via KubeDiagrams."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from kubeoptix_core_ai.visualization.kubediagrams.config import bundled_config_path
from kubeoptix_core_ai.visualization.png.assets import safe_asset_filename

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

        render_manifests = valid_manifests
        temporary_dir: tempfile.TemporaryDirectory[str] | None = None
        if self._env_flag(_ENV_ENRICH_LABELS, default=True):
            render_manifests, temporary_dir = self._build_enriched_manifest_set(valid_manifests)

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
            try:
                docs = list(yaml.safe_load_all(source.read_text(encoding="utf-8")))
            except (OSError, yaml.YAMLError):
                continue
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
        return changed

    def _enrich_manifest_yaml_text(self, content: str, source_path: Path) -> str | None:
        try:
            documents = list(yaml.safe_load_all(content))
        except yaml.YAMLError:
            return None
        if not documents:
            return None

        changed = False
        normalized: list[object] = []
        for document in documents:
            if not isinstance(document, dict):
                normalized.append(document)
                continue
            if self._normalize_manifest_document(document):
                changed = True
            normalized.append(document)

        if not changed:
            return None
        return yaml.safe_dump_all(normalized, sort_keys=False, allow_unicode=False)

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

    def _collect_pod_grouping(self, manifests: tuple[Path, ...]) -> tuple[dict[Path, int], set[Path]]:
        counts: dict[str, int] = {}
        representative: dict[str, Path] = {}

        for source in manifests:
            raw = str(source).lower()
            if "/pods/" not in raw:
                continue
            try:
                content = source.read_text(encoding="utf-8")
                docs = list(yaml.safe_load_all(content))
            except (OSError, yaml.YAMLError):
                continue
            pod_doc = next((d for d in docs if isinstance(d, dict) and d.get("kind") == "Pod"), None)
            if not isinstance(pod_doc, dict):
                continue
            metadata = pod_doc.get("metadata")
            if not isinstance(metadata, dict):
                continue
            pod_name = str(metadata.get("name") or source.stem)
            group_key = self._pod_group_key(pod_name)
            counts[group_key] = counts.get(group_key, 0) + 1
            representative.setdefault(group_key, source)

        representative_set = set(representative.values())
        count_by_path = {
            path: counts[group_key]
            for group_key, path in representative.items()
        }
        return count_by_path, representative_set

    def _build_enriched_manifest_set(
        self, manifests: tuple[Path, ...]
    ) -> tuple[tuple[Path, ...], tempfile.TemporaryDirectory[str] | None]:
        temp_dir = tempfile.TemporaryDirectory(prefix="kd_enriched_")
        output_root = Path(temp_dir.name)
        enriched_paths: list[Path] = []
        changed = False
        pod_count_by_path, pod_representatives = self._collect_pod_grouping(manifests)
        external_peers = self._collect_external_peer_manifests(manifests)

        for idx, source in enumerate(manifests):
            raw_source = str(source).lower()
            if "/pods/" in raw_source and source not in pod_representatives:
                changed = True
                continue
            try:
                content = source.read_text(encoding="utf-8")
            except OSError:
                enriched_paths.append(source)
                continue

            enriched = self._enrich_manifest_yaml_text(content, source)
            if source in pod_count_by_path:
                if enriched is None:
                    enriched = content
                try:
                    docs = list(yaml.safe_load_all(enriched))
                except yaml.YAMLError:
                    docs = []
                patched_docs: list[object] = []
                patched = False
                for document in docs:
                    if not isinstance(document, dict) or document.get("kind") != "Pod":
                        patched_docs.append(document)
                        continue
                    metadata = document.get("metadata")
                    if not isinstance(metadata, dict):
                        metadata = {}
                        document["metadata"] = metadata
                    labels = metadata.get("labels")
                    if not isinstance(labels, dict):
                        labels = {}
                        metadata["labels"] = labels
                    labels["kubeoptix.io/pod-group-size"] = str(pod_count_by_path[source])
                    labels["kubeoptix.io/pod-group"] = self._pod_group_key(
                        str(metadata.get("name") or source.stem)
                    )
                    patched_docs.append(document)
                    patched = True
                if patched:
                    enriched = yaml.safe_dump_all(
                        patched_docs, sort_keys=False, allow_unicode=False
                    )

            if enriched is None:
                enriched_paths.append(source)
                continue

            target = output_root / f"{idx:04d}_{source.name}"
            target.write_text(enriched, encoding="utf-8")
            enriched_paths.append(target)
            changed = True

        for peer_idx, peer in enumerate(external_peers):
            target = output_root / f"ext_{peer_idx:04d}_{peer['metadata']['name']}.yaml"
            target.write_text(
                yaml.safe_dump(peer, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
            enriched_paths.append(target)
            changed = True

        if not changed:
            temp_dir.cleanup()
            return manifests, None
        return tuple(enriched_paths), temp_dir

    def _filter_parseable_manifests(self, manifests: tuple[Path, ...]) -> tuple[Path, ...]:
        valid: list[Path] = []
        for path in manifests:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Manifest ignorado (erro de leitura): %s (%s)", path, exc)
                continue
            try:
                docs = list(yaml.safe_load_all(content))
            except yaml.YAMLError as exc:
                logger.warning("Manifest ignorado (YAML inválido): %s (%s)", path, exc)
                continue
            if not docs or all(doc is None for doc in docs):
                logger.warning("Manifest ignorado (vazio): %s", path)
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
        if shutil.which("kube-diagrams") and shutil.which("dot"):
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

        return True
