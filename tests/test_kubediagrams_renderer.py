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
    png_commands = [
        call.args[0]
        for call in run_mock.call_args_list
        if call.args and "png" in call.args[0]
    ]
    assert png_commands
    command = png_commands[-1]
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
        "{ this is not recoverable yaml [[[",
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
    assert "kubeoptix.io/cat-workloads: Workloads" in rendered
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
    assert "kubeoptix.io/pod-group-size: '2'" in merged_content or "kubeoptix.io/pod-group-size: \"2\"" in merged_content or "kubeoptix.io/pod-group-size: 2" in merged_content
    assert "kubeoptix.io/pod-group: payment-api" in merged_content
    assert "payment-api (2 replicas)" in merged_content
    assert "kubeoptix.io/cat-pods: Pods" in merged_content
    assert "kubeoptix.io/cat-workloads: Workloads" in merged_content


def test_bundled_kube_diagrams_config_defines_category_clusters() -> None:
    from kubeoptix_core_ai.visualization.kubediagrams.config import bundled_config_path
    import yaml

    config_path = bundled_config_path()
    assert config_path is not None
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "nodes" in loaded
    assert "clusters" in loaded
    labels = {item.get("label") for item in loaded["clusters"] if isinstance(item, dict)}
    assert "kubeoptix.io/cat-workloads" in labels
    assert "kubeoptix.io/cat-networking" in labels
    assert "kubeoptix.io/cat-storage" in labels
    assert "kubeoptix.io/cat-config" in labels
    assert "kubeoptix.io/cat-build" not in labels
    cluster_labels = [
        item.get("label") for item in loaded["clusters"] if isinstance(item, dict)
    ]
    assert cluster_labels.index("kubeoptix.io/cat-workloads") < cluster_labels.index(
        "kubeoptix.io/cat-config"
    )
    assert cluster_labels.index("kubeoptix.io/cat-config") < cluster_labels.index(
        "kubeoptix.io/cat-storage"
    )
    assert cluster_labels.index("kubeoptix.io/cat-storage") < cluster_labels.index(
        "kubeoptix.io/cat-networking"
    )
    assert cluster_labels.index("kubeoptix.io/cat-networking") < cluster_labels.index(
        "kubeoptix.io/cat-nodes"
    )
    assert "Node/v1" in loaded["nodes"]
    assert "Route/route.openshift.io/v1" in loaded["nodes"]
    assert loaded["nodes"]["BuildConfig/build.openshift.io/v1"]["show"] is False


def test_tune_dot_layout_architecture_profile_uses_high_resolution_layout() -> None:
    renderer = KubeDiagramsRenderer(Path("/tmp"), namespace="shiftwise-ai")
    source = (
        "digraph {\n"
        '\tgraph [fontcolor="#2D3436" rankdir=TB splines=line]\n'
        '\tsubgraph "cluster_Namespace: shiftwise-ai" {\n'
        '\t\tgraph [bgcolor=white rankdir=LR tooltip="Namespace: shiftwise-ai"]\n'
        "\t}\n"
        "}\n"
    )
    tuned = renderer._tune_dot_layout(source, layout_profile="architecture")
    assert "dpi=120" in tuned
    assert "splines=polyline" in tuned
    assert "nodesep=0.45" in tuned
    assert "ranksep=0.85" in tuned
    assert 'size="16.0,6.5"' in tuned
    assert "rankdir=TB" in tuned
    assert "rankdir=LR" not in tuned
    assert "ratio=compress" in tuned
    assert "pad=0.12" in tuned


def test_tune_dot_layout_forces_horizontal_rankdir() -> None:
    renderer = KubeDiagramsRenderer(Path("/tmp"), namespace="shiftwise-ai")
    source = (
        "digraph {\n"
        '\tsubgraph "cluster_Namespace: shiftwise-ai" {\n'
        '\t\tgraph [bgcolor=white rankdir=LR tooltip="Namespace: shiftwise-ai"]\n'
        "\t}\n"
        "}\n"
    )
    tuned = renderer._tune_dot_layout(source)
    assert "rankdir=LR" in tuned
    assert "rankdir=TB" not in tuned


def test_tune_dot_layout_sequences_clusters_horizontally() -> None:
    renderer = KubeDiagramsRenderer(Path("/tmp"), namespace="shiftwise-ai")
    source = """digraph {
	graph [fontcolor="#2D3436" rankdir=TB splines=ortho]
	subgraph "cluster_Namespace: ns" {
		graph [bgcolor=white rankdir=LR tooltip="Namespace: ns"]
		subgraph cluster_Configuration {
			graph [label=Configuration rank=min]
			"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" [label="cm"]
		}
		subgraph cluster_Workloads {
			graph [label=Workloads]
			bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb [label="sts"]
			subgraph cluster_Pods {
				graph [label=Pods]
				"cccccccccccccccccccccccccccccccc" [label="pod"]
			}
		}
		subgraph cluster_Networking {
			graph [label=Networking]
			"dddddddddddddddddddddddddddddddd" [label="svc"]
		}
		subgraph cluster_Storage {
			graph [label=Storage]
			"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" [label="pvc"]
		}
	}
	bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb -> "cccccccccccccccccccccccccccccccc" [style=dotted]
	bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb -> "dddddddddddddddddddddddddddddddd" [style=solid]
	"cccccccccccccccccccccccccccccccc" -> "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" [style=solid]
	"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" -> bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb [style=solid]
}
"""
    tuned = renderer._tune_dot_layout(source)
    workloads_idx = tuned.find("subgraph cluster_Workloads")
    config_idx = tuned.find("subgraph cluster_Configuration")
    storage_idx = tuned.find("subgraph cluster_Storage")
    networking_idx = tuned.find("subgraph cluster_Networking")
    assert 0 <= workloads_idx < config_idx < storage_idx < networking_idx
    assert "cluster_kubeoptix_left" not in tuned
    assert "rank=min" not in tuned
    assert "newrank=true" in tuned
    assert "compound=true" in tuned
    assert "constraint=false" in tuned
    assert "style=invis weight=200 minlen=1" in tuned
    assert "cccccccccccccccccccccccccccccccc" in tuned
    assert "style=invis" in tuned


def test_tune_dot_layout_wraps_long_ranks_into_grid() -> None:
    renderer = KubeDiagramsRenderer(Path("/tmp"), namespace="shiftwise-ai")
    pod_ids = [f'"{"a" * 30}{index:02x}"' for index in range(1, 11)]
    pod_nodes = "\n".join(f"\t\t\t{node_id} [label=\"p{index}\"]" for index, node_id in enumerate(pod_ids, start=1))
    source = f"""digraph {{
	graph [fontcolor="#2D3436" rankdir=TB splines=line]
	subgraph cluster_Workloads {{
		graph [label=Workloads]
		bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb [label="deploy"]
		subgraph cluster_Pods {{
			graph [label=Pods]
{pod_nodes}
		}}
	}}
}}
"""
    tuned = renderer._tune_dot_layout(source, layout_profile="architecture")
    assert tuned.count("rank=same") == 2
    assert f"{pod_ids[0]} -> {pod_ids[8]}" in tuned
    assert "rankdir=TB" in tuned
    assert "rankdir=LR" not in tuned


def test_render_manifests_recovers_placeholder_sanitized_pods(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="shiftwise-ai",
        path_prefix="assets",
    )
    pods_dir = tmp_path / "resources" / "pods"
    pods_dir.mkdir(parents=True)
    pod = pods_dir / "kubeoptix-harvester-0.yaml"
    pod.write_text(
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        "  name: kubeoptix-harvester-0\n"
        "  namespace: shiftwise-ai\n"
        "  labels:\n"
        "    app.kubernetes.io/name: kubeoptix-harvester\n"
        "  uid: [RG_REMOVIDO]-0a35-4eff-90af-458990df5b00\n"
        "spec:\n"
        "  serviceAccountName: shiftwisea-ai-user\n"
        "  securityContext:\n"
        "    runAsUser: [TELEFONE_REMOVIDO]\n"
        "  volumes:\n"
        "  - name: kube-api-access\n"
        "    projected:\n"
        "      sources:\n"
        "      - [TOKEN_EXPLICITO_REMOVIDO]: 3607\n"
        "          path: token\n",
        encoding="utf-8",
    )

    used_contents: list[str] = []

    def _fake_run(command, **kwargs):
        for item in command:
            path = Path(str(item))
            if path.suffix == ".yaml" and path.is_file():
                used_contents.append(path.read_text(encoding="utf-8"))
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
        rel = renderer.render_manifests("pods", (pod,))

    assert rel == "assets/pods.png"
    merged = "\n".join(used_contents)
    assert "kubeoptix-harvester" in merged
    assert "kind: Pod" in merged


def test_render_manifests_appends_service_ports_and_patches_routes(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    renderer = KubeDiagramsRenderer(
        assets_dir,
        namespace="shiftwise-ai",
        path_prefix="assets",
    )
    services_dir = tmp_path / "resources" / "services"
    routes_dir = tmp_path / "resources" / "routes.route.openshift.io"
    services_dir.mkdir(parents=True)
    routes_dir.mkdir(parents=True)
    service = services_dir / "harvester-api.yaml"
    route = routes_dir / "harvester.yaml"
    service.write_text(
        "apiVersion: v1\n"
        "kind: Service\n"
        "metadata:\n"
        "  name: harvester-api\n"
        "  namespace: shiftwise-ai\n"
        "spec:\n"
        "  ports:\n"
        "  - name: http\n"
        "    port: 8000\n"
        "    targetPort: 8000\n",
        encoding="utf-8",
    )
    route.write_text(
        "apiVersion: route.openshift.io/v1\n"
        "kind: Route\n"
        "metadata:\n"
        "  name: harvester\n"
        "  namespace: shiftwise-ai\n"
        "spec:\n"
        "  to:\n"
        "    kind: Service\n"
        "    name: harvester-api\n",
        encoding="utf-8",
    )

    used_contents: list[str] = []

    def _fake_run(command, **kwargs):
        for item in command:
            path = Path(str(item))
            if path.suffix in {".yaml", ".yml"} and path.is_file():
                used_contents.append(path.read_text(encoding="utf-8"))
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
        rel = renderer.render_manifests("net", (service, route))

    assert rel == "assets/net.png"
    merged = "\n".join(used_contents)
    assert "harvester-api:8000" in merged
    assert "kind: Route" in merged
    assert "kind: Service" in merged

