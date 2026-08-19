"""Testes do renderizador KubeDiagrams."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kubeoptix_core_ai.visualization.kubediagrams.renderer import (
    KubeDiagramsRenderer,
    is_kubediagrams_available,
)


def test_is_kubediagrams_available_requires_dot_and_cli() -> None:
    with (
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.find_container_runtime",
            return_value=None,
        ),
        patch("kubeoptix_core_ai.visualization.kubediagrams.renderer.shutil.which") as which,
    ):
        which.side_effect = lambda name: "/usr/bin/kube-diagrams" if name == "kube-diagrams" else None
        assert not is_kubediagrams_available()

        which.side_effect = lambda name: "/usr/bin/dot" if name == "dot" else None
        assert not is_kubediagrams_available()

        which.side_effect = lambda name: f"/usr/bin/{name}"
        assert is_kubediagrams_available()


def test_is_kubediagrams_available_accepts_container_runtime() -> None:
    with (
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.find_container_runtime",
            return_value="podman",
        ),
        patch("kubeoptix_core_ai.visualization.kubediagrams.renderer.shutil.which", return_value=None),
    ):
        assert is_kubediagrams_available()


def test_render_namespace_architecture_invokes_cli(tmp_path: Path) -> None:
    namespace_root = tmp_path / "ns"
    (namespace_root / "apps" / "api" / "deployments").mkdir(parents=True)
    manifest = namespace_root / "apps" / "api" / "deployments" / "api.yaml"
    manifest.write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n",
        encoding="utf-8",
    )

    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="example-ns",
        path_prefix="assets",
    )

    def _fake_run(command, **kwargs):
        output = Path(command[command.index("-o") + 1])
        output.write_bytes(b"png")
        class _Result:
            returncode = 0
            stderr = ""

        return _Result()

    with (
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.is_kubediagrams_available",
            return_value=True,
        ),
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.shutil.which",
            side_effect=lambda name: f"/usr/bin/{name}",
        ),
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.find_kube_diagrams_executable",
            return_value="/usr/bin/kube-diagrams",
        ),
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.subprocess.run",
            side_effect=_fake_run,
        ) as run_mock,
    ):
        rel = renderer.render_namespace_architecture(namespace_root)

    assert rel == "assets/namespace_architecture.png"
    run_mock.assert_called_once()
    command = run_mock.call_args.args[0]
    assert command[0] == "/usr/bin/kube-diagrams"
    assert "-f" in command and "png" in command
    assert "-n" in command and "example-ns" in command


def test_render_manifests_retries_without_config_when_config_fails(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="example-ns",
        path_prefix="assets",
    )
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: svc\n",
        encoding="utf-8",
    )
    output_file = assets_dir / "comm.png"

    def _local_attempt(manifests, output_path, *, use_config):
        if use_config:
            return False
        output_file.write_bytes(b"png")
        return True

    with (
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.is_kubediagrams_available",
            return_value=True,
        ),
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.shutil.which",
            side_effect=lambda name: f"/usr/bin/{name}" if name in {"kube-diagrams", "dot"} else None,
        ),
        patch.object(
            renderer,
            "_invoke_local_kube_diagrams",
            side_effect=_local_attempt,
        ) as local_mock,
        patch(
            "kubeoptix_core_ai.visualization.kubediagrams.renderer.find_container_runtime",
            return_value=None,
        ),
    ):
        rel = renderer.render_manifests("comm", (manifest,))

    assert rel == "assets/comm.png"
    assert local_mock.call_count == 2
