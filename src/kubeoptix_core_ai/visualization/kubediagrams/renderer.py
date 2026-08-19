"""Renderização de diagramas de arquitetura via KubeDiagrams."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from kubeoptix_core_ai.visualization.kubediagrams.config import bundled_config_path
from kubeoptix_core_ai.visualization.png.assets import safe_asset_filename

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 180
KUBEDIAGRAMS_IMAGE = "docker.io/philippemerle/kubediagrams:latest"


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
        if not is_kubediagrams_available():
            logger.debug("KubeDiagrams indisponível (sem CLI/dot nem container runtime)")
            return None
        if not manifests:
            logger.debug("Nenhum manifest fornecido para %s", viz_id)
            return None

        output_path = self._output_path(viz_id)
        if not self._invoke_kube_diagrams(manifests, output_path):
            return None
        return self._relative_path(viz_id)

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
            "-n",
            self._namespace,
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
            "-n",
            self._namespace,
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
            return False

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            logger.warning(
                "KubeDiagrams retornou código %s: %s",
                result.returncode,
                stderr[:500] if stderr else "(sem stderr)",
            )
            return False

        if not output_path.is_file() or output_path.stat().st_size <= 0:
            logger.warning("KubeDiagrams não produziu arquivo PNG: %s", output_path)
            return False

        return True
