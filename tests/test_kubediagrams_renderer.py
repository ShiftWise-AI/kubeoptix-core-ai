"""Testes do renderizador KubeDiagrams."""

from __future__ import annotations

import os
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
    assert "-n" not in command


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


def test_render_manifests_skips_invalid_yaml_and_uses_valid_files(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="example-ns",
        path_prefix="assets",
    )
    valid_manifest = tmp_path / "valid.yaml"
    valid_manifest.write_text(
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: svc\n",
        encoding="utf-8",
    )
    invalid_manifest = tmp_path / "invalid.yaml"
    invalid_manifest.write_text(
        "apiVersion: v1\nkind: Service\nmetadata:\n\tname: svc\n",  # tab invalida em YAML
        encoding="utf-8",
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
        rel = renderer.render_manifests("filtered", (invalid_manifest, valid_manifest))

    assert rel == "assets/filtered.png"
    command = run_mock.call_args.args[0]
    manifest_args = [arg for arg in command if arg.endswith(".yaml")]
    assert len(manifest_args) == 1
    assert "valid.yaml" in manifest_args[0]


def test_render_manifests_normalizes_namespace_without_clustering_labels(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="example-ns",
        path_prefix="assets",
    )
    manifest = tmp_path / "deployment.yaml"
    original = (
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        "  name: api\n"
        "  labels:\n"
        "    app.kubernetes.io/name: api\n"
        "    helm.sh/chart: api-0.1.0\n"
        "spec:\n"
        "  replicas: 1\n"
    )
    manifest.write_text(original, encoding="utf-8")

    captured_manifest_path: Path | None = None
    rendered_manifest_content: str | None = None

    def _fake_run(command, **kwargs):
        nonlocal captured_manifest_path, rendered_manifest_content
        captured_manifest_path = Path(command[-1])
        rendered_manifest_content = captured_manifest_path.read_text(encoding="utf-8")
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
        ),
    ):
        rel = renderer.render_manifests("enriched", (manifest,))

    assert rel == "assets/enriched.png"
    assert captured_manifest_path is not None
    assert str(captured_manifest_path) != str(manifest)

    assert rendered_manifest_content is not None
    rendered = rendered_manifest_content
    assert "namespace: example-ns" in rendered
    assert "app.kubernetes.io/name" not in rendered
    assert "helm.sh/chart" not in rendered
    assert manifest.read_text(encoding="utf-8") == original


def test_render_manifests_injects_external_namespace_peer(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="example-ns",
        path_prefix="assets",
    )
    manifest = tmp_path / "externalname-svc.yaml"
    manifest.write_text(
        "apiVersion: v1\n"
        "kind: Service\n"
        "metadata:\n"
        "  name: public-api\n"
        "spec:\n"
        "  type: ExternalName\n"
        "  externalName: api.vendor.example.com\n",
        encoding="utf-8",
    )

    used_manifest_contents: list[str] = []

    def _fake_run(command, **kwargs):
        nonlocal used_manifest_contents
        used_manifest_contents = [
            Path(arg).read_text(encoding="utf-8")
            for arg in command
            if str(arg).endswith(".yaml")
        ]
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
        ),
    ):
        rel = renderer.render_manifests("external", (manifest,))

    assert rel == "assets/external.png"
    merged = "\n".join(used_manifest_contents)
    assert "namespace: external" in merged
    assert "externalName: api.vendor.example.com" in merged


def test_render_manifests_can_disable_label_enrichment_by_env(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="example-ns",
        path_prefix="assets",
    )
    manifest = tmp_path / "service.yaml"
    manifest.write_text(
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: svc\n",
        encoding="utf-8",
    )

    captured_manifest_path: Path | None = None

    def _fake_run(command, **kwargs):
        nonlocal captured_manifest_path
        captured_manifest_path = Path(command[-1])
        output = Path(command[command.index("-o") + 1])
        output.write_bytes(b"png")

        class _Result:
            returncode = 0
            stderr = ""

        return _Result()

    with (
        patch.dict(os.environ, {"KUBEOPTIX_DIAGRAM_ENRICH_LABELS": "false"}),
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
        ),
    ):
        rel = renderer.render_manifests("plain", (manifest,))

    assert rel == "assets/plain.png"
    assert captured_manifest_path is not None
    assert str(captured_manifest_path) == str(manifest)


def test_render_manifests_groups_equivalent_pods_with_count_label(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="example-ns",
        path_prefix="assets",
    )
    pods_dir = tmp_path / "resources" / "pods"
    pods_dir.mkdir(parents=True)
    pod_a = pods_dir / "pod-a.yaml"
    pod_b = pods_dir / "pod-b.yaml"
    pod_c = pods_dir / "pod-c.yaml"
    pod_a.write_text(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: payment-api-7f98c8d4c9-abcde\n",
        encoding="utf-8",
    )
    pod_b.write_text(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: payment-api-7f98c8d4c9-fghij\n",
        encoding="utf-8",
    )
    pod_c.write_text(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: invoice-api-7f98c8d4c9-klmno\n",
        encoding="utf-8",
    )

    used_manifest_paths: list[Path] = []
    used_manifest_contents: list[str] = []

    def _fake_run(command, **kwargs):
        nonlocal used_manifest_paths, used_manifest_contents
        used_manifest_paths = [Path(arg) for arg in command if str(arg).endswith(".yaml")]
        used_manifest_contents = [path.read_text(encoding="utf-8") for path in used_manifest_paths]
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
        ),
    ):
        rel = renderer.render_manifests("pods", (pod_a, pod_b, pod_c))

    assert rel == "assets/pods.png"
    assert len(used_manifest_paths) == 2
    merged_content = "\n".join(used_manifest_contents)
    assert "kubeoptix.io/pod-group-size: '2'" in merged_content
    assert "kubeoptix.io/pod-group: payment-api" in merged_content
