"""Testes da seleção de manifests para KubeDiagrams."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from kubeoptix_core_ai.visualization.kubediagrams.manifests import select_architecture_manifests

from tests.conftest import EXAMPLE_NAMESPACE

FIXTURES = Path(__file__).parent / "fixtures"
TRAINING_NAMESPACE_ROOT = Path(
    "/home/parraes/redhat/shiftwise-ai/base-treinamento/plfat-tbforte"
)


@pytest.fixture
def architecture_tree(tmp_path: Path) -> Path:
    base = tmp_path / "metadados"
    ns = base / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (app / "services").mkdir(parents=True)
    (app / "routes").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "deployment_backend_acesso_app.yaml",
        app / "deployments" / "backend-acesso-app.yaml",
    )
    shutil.copy(
        FIXTURES / "service_backend_acesso_app.yaml",
        app / "services" / "backend-acesso-app.yaml",
    )
    shutil.copy(
        FIXTURES / "route_backend_acesso_app.yaml",
        app / "routes" / "backend-acesso-app.yaml",
    )
    return ns


def test_select_architecture_manifests_includes_workload_service_route(
    architecture_tree: Path,
) -> None:
    manifests = select_architecture_manifests(architecture_tree)
    paths = {path.name for path in manifests}

    assert "backend-acesso-app.yaml" in paths
    assert len(manifests) >= 3
    assert not any("replicaset" in str(path).lower() for path in manifests)


def test_select_architecture_manifests_includes_supporting_inventory_resources(
    tmp_path: Path,
) -> None:
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (app / "services").mkdir(parents=True)
    (app / "configmaps").mkdir(parents=True)
    (app / "secrets").mkdir(parents=True)
    (app / "hpa").mkdir(parents=True)
    (app / "vpa").mkdir(parents=True)
    (app / "pdb").mkdir(parents=True)
    (ns / "resources" / "persistentvolumeclaims").mkdir(parents=True)
    (ns / "resources" / "pods").mkdir(parents=True)
    (ns / "resources" / "pods.metrics.k8s.io").mkdir(parents=True)
    (ns / "resources" / "clusterserviceversions.operators.coreos.com").mkdir(parents=True)

    (app / "deployments" / "backend-acesso-app.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "services" / "backend-acesso-app.yaml").write_text(
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "backend-acesso-app-cm.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: backend-acesso-app-cm\n",
        encoding="utf-8",
    )
    (app / "secrets" / "backend-acesso-app-secret.yaml").write_text(
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: backend-acesso-app-secret\n",
        encoding="utf-8",
    )
    (ns / "resources" / "persistentvolumeclaims" / "data-backend-acesso-app.yaml").write_text(
        "apiVersion: v1\nkind: PersistentVolumeClaim\nmetadata:\n  name: data-backend-acesso-app\n",
        encoding="utf-8",
    )
    (ns / "resources" / "pods" / "backend-acesso-app-12345.yaml").write_text(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: backend-acesso-app-12345\n",
        encoding="utf-8",
    )
    (app / "hpa" / "backend-acesso-app.yaml").write_text(
        "apiVersion: autoscaling/v2\nkind: HorizontalPodAutoscaler\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "vpa" / "backend-acesso-app.yaml").write_text(
        "apiVersion: autoscaling.k8s.io/v1\nkind: VerticalPodAutoscaler\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "pdb" / "backend-acesso-app.yaml").write_text(
        "apiVersion: policy/v1\nkind: PodDisruptionBudget\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    # Não deve entrar no diagrama de arquitetura.
    (ns / "resources" / "pods.metrics.k8s.io" / "pod-metrics.yaml").write_text(
        "apiVersion: metrics.k8s.io/v1beta1\nkind: PodMetrics\nmetadata:\n  name: pod-metrics\n",
        encoding="utf-8",
    )
    (ns / "resources" / "clusterserviceversions.operators.coreos.com" / "csv.yaml").write_text(
        "apiVersion: operators.coreos.com/v1alpha1\nkind: ClusterServiceVersion\nmetadata:\n  name: csv\n",
        encoding="utf-8",
    )

    manifests = select_architecture_manifests(ns)
    paths = {str(path) for path in manifests}

    assert any("/deployments/" in path for path in paths)
    assert any("/services/" in path for path in paths)
    assert any("/configmaps/" in path for path in paths)
    assert any("/secrets/" in path for path in paths)
    assert any("/persistentvolumeclaims/" in path for path in paths)
    assert any("/pods/" in path for path in paths)
    assert any("/hpa/" in path for path in paths)
    assert any("/vpa/" in path for path in paths)
    assert any("/pdb/" in path for path in paths)
    assert not any("pods.metrics.k8s.io" in path for path in paths)
    assert not any("clusterserviceversions.operators.coreos.com" in path for path in paths)


def test_select_architecture_manifests_includes_additional_inventory_kinds(
    tmp_path: Path,
) -> None:
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (ns / "resources" / "ingresses.networking.k8s.io").mkdir(parents=True)
    (ns / "resources" / "networkpolicies.networking.k8s.io").mkdir(parents=True)
    (ns / "resources" / "serviceaccounts").mkdir(parents=True)
    (ns / "resources" / "persistentvolumes").mkdir(parents=True)
    (ns / "resources" / "storageclasses.storage.k8s.io").mkdir(parents=True)
    (ns / "resources" / "packagemanifests.packages.operators.coreos.com").mkdir(parents=True)

    (app / "deployments" / "backend-acesso-app.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (ns / "resources" / "ingresses.networking.k8s.io" / "backend-ingress.yaml").write_text(
        "apiVersion: networking.k8s.io/v1\nkind: Ingress\nmetadata:\n  name: backend-ingress\n",
        encoding="utf-8",
    )
    (ns / "resources" / "networkpolicies.networking.k8s.io" / "backend-netpol.yaml").write_text(
        "apiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\nmetadata:\n  name: backend-netpol\n",
        encoding="utf-8",
    )
    (ns / "resources" / "serviceaccounts" / "backend-sa.yaml").write_text(
        "apiVersion: v1\nkind: ServiceAccount\nmetadata:\n  name: backend-sa\n",
        encoding="utf-8",
    )
    (ns / "resources" / "persistentvolumes" / "backend-pv.yaml").write_text(
        "apiVersion: v1\nkind: PersistentVolume\nmetadata:\n  name: backend-pv\n",
        encoding="utf-8",
    )
    (ns / "resources" / "storageclasses.storage.k8s.io" / "backend-sc.yaml").write_text(
        "apiVersion: storage.k8s.io/v1\nkind: StorageClass\nmetadata:\n  name: backend-sc\n",
        encoding="utf-8",
    )
    (ns / "resources" / "packagemanifests.packages.operators.coreos.com" / "pm.yaml").write_text(
        "apiVersion: packages.operators.coreos.com/v1\nkind: PackageManifest\nmetadata:\n  name: pm\n",
        encoding="utf-8",
    )

    manifests = select_architecture_manifests(ns)
    paths = {str(path) for path in manifests}

    assert any("/ingresses.networking.k8s.io/" in path for path in paths)
    assert any("/networkpolicies.networking.k8s.io/" in path for path in paths)
    assert any("/serviceaccounts/" in path for path in paths)
    assert any("/persistentvolumes/" in path for path in paths)
    assert any("/storageclasses.storage.k8s.io/" in path for path in paths)
    assert not any("packagemanifests.packages.operators.coreos.com" in path for path in paths)


def test_select_architecture_manifests_excludes_noisy_derived_resources(
    tmp_path: Path,
) -> None:
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (ns / "resources" / "replicasets.apps").mkdir(parents=True)
    (ns / "resources" / "endpointslices.discovery.k8s.io").mkdir(parents=True)
    (ns / "resources" / "endpoints").mkdir(parents=True)
    (ns / "resources" / "leases.coordination.k8s.io").mkdir(parents=True)
    (ns / "resources" / "ingresses.networking.k8s.io").mkdir(parents=True)

    (app / "deployments" / "backend-acesso-app.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (ns / "resources" / "replicasets.apps" / "backend-rs.yaml").write_text(
        "apiVersion: apps/v1\nkind: ReplicaSet\nmetadata:\n  name: backend-rs\n",
        encoding="utf-8",
    )
    (ns / "resources" / "endpointslices.discovery.k8s.io" / "backend-es.yaml").write_text(
        "apiVersion: discovery.k8s.io/v1\nkind: EndpointSlice\nmetadata:\n  name: backend-es\n",
        encoding="utf-8",
    )
    (ns / "resources" / "endpoints" / "backend-ep.yaml").write_text(
        "apiVersion: v1\nkind: Endpoints\nmetadata:\n  name: backend-ep\n",
        encoding="utf-8",
    )
    (ns / "resources" / "leases.coordination.k8s.io" / "backend-lease.yaml").write_text(
        "apiVersion: coordination.k8s.io/v1\nkind: Lease\nmetadata:\n  name: backend-lease\n",
        encoding="utf-8",
    )
    (ns / "resources" / "ingresses.networking.k8s.io" / "backend-ingress.yaml").write_text(
        "apiVersion: networking.k8s.io/v1\nkind: Ingress\nmetadata:\n  name: backend-ingress\n",
        encoding="utf-8",
    )

    manifests = select_architecture_manifests(ns)
    paths = {str(path) for path in manifests}

    assert any("/deployments/" in path for path in paths)
    assert any("/ingresses.networking.k8s.io/" in path for path in paths)
    assert not any("/replicasets.apps/" in path for path in paths)
    assert not any("/endpointslices.discovery.k8s.io/" in path for path in paths)
    assert not any("/endpoints/" in path for path in paths)
    assert not any("/leases.coordination.k8s.io/" in path for path in paths)


def test_select_architecture_manifests_prioritizes_layered_order(
    tmp_path: Path,
) -> None:
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (app / "services").mkdir(parents=True)
    (app / "routes").mkdir(parents=True)
    (app / "configmaps").mkdir(parents=True)

    (app / "deployments" / "backend-acesso-app.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "services" / "backend-acesso-app.yaml").write_text(
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "routes" / "backend-acesso-app.yaml").write_text(
        "apiVersion: route.openshift.io/v1\nkind: Route\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "backend-acesso-app-cm.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: backend-acesso-app-cm\n",
        encoding="utf-8",
    )

    manifests = select_architecture_manifests(ns)
    ordered = [str(path) for path in manifests]

    route_idx = next(i for i, p in enumerate(ordered) if "/routes/" in p)
    service_idx = next(i for i, p in enumerate(ordered) if "/services/" in p)
    workload_idx = next(i for i, p in enumerate(ordered) if "/deployments/" in p)
    configmap_idx = next(i for i, p in enumerate(ordered) if "/configmaps/" in p)

    assert route_idx < service_idx < workload_idx < configmap_idx


def test_select_architecture_manifests_excludes_common_ocp_artifacts(
    tmp_path: Path,
) -> None:
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (app / "configmaps").mkdir(parents=True)
    (app / "secrets").mkdir(parents=True)

    (app / "deployments" / "backend-acesso-app.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "kube-root-ca.crt.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: kube-root-ca.crt\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "backend-config.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: backend-config\n",
        encoding="utf-8",
    )
    (app / "secrets" / "default-token-abcd1.yaml").write_text(
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: default-token-abcd1\n",
        encoding="utf-8",
    )
    (app / "secrets" / "backend-secret.yaml").write_text(
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: backend-secret\n",
        encoding="utf-8",
    )

    manifests = select_architecture_manifests(ns)
    names = {path.name for path in manifests}

    assert "backend-acesso-app.yaml" in names
    assert "backend-config.yaml" in names
    assert "backend-secret.yaml" in names
    assert "kube-root-ca.crt.yaml" not in names
    assert "default-token-abcd1.yaml" not in names


def test_select_architecture_manifests_excludes_global_no_app_objects(
    tmp_path: Path,
) -> None:
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (app / "configmaps").mkdir(parents=True)
    (ns / "apps" / "__sem_app__" / "configmaps").mkdir(parents=True)
    (ns / "apps" / "_no_app_" / "secrets").mkdir(parents=True)
    (ns / "apps" / "__no_app__" / "configmaps").mkdir(parents=True)

    (app / "deployments" / "backend-acesso-app.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "global-ca.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: global-ca\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "kubeoptix-core-ai-2-global-ca.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: kubeoptix-core-ai-2-global-ca\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "kubeoptix-core-ai-2-sys-config.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: kubeoptix-core-ai-2-sys-config\n",
        encoding="utf-8",
    )
    (ns / "apps" / "__sem_app__" / "configmaps" / "sys-config.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: sys-config\n",
        encoding="utf-8",
    )
    (ns / "apps" / "_no_app_" / "secrets" / "shared-secret.yaml").write_text(
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: shared-secret\n",
        encoding="utf-8",
    )
    (ns / "apps" / "__no_app__" / "configmaps" / "global-ca.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: global-ca\n",
        encoding="utf-8",
    )

    manifests = select_architecture_manifests(ns)
    paths = {str(path) for path in manifests}

    assert any("/deployments/" in path for path in paths)
    assert not any("global-ca.yaml" in path for path in paths)
    assert not any("kubeoptix-core-ai-2-global-ca.yaml" in path for path in paths)
    assert not any("kubeoptix-core-ai-2-sys-config.yaml" in path for path in paths)
    assert not any("/apps/__sem_app__/" in path for path in paths)
    assert not any("/apps/_no_app_/" in path for path in paths)
    assert not any("/apps/__no_app__/" in path for path in paths)


def test_select_architecture_manifests_can_include_common_ocp_by_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (app / "configmaps").mkdir(parents=True)

    (app / "deployments" / "backend-acesso-app.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "kube-root-ca.crt.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: kube-root-ca.crt\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("KUBEOPTIX_DIAGRAM_INCLUDE_COMMON_OCP", "true")
    manifests = select_architecture_manifests(ns)
    names = {path.name for path in manifests}
    assert "kube-root-ca.crt.yaml" in names


def test_select_architecture_manifests_env_include_overrides_exclude(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ns = tmp_path / EXAMPLE_NAMESPACE
    app = ns / "apps" / "backend-acesso-app"
    (app / "deployments").mkdir(parents=True)
    (app / "configmaps").mkdir(parents=True)

    (app / "deployments" / "backend-acesso-app.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: backend-acesso-app\n",
        encoding="utf-8",
    )
    (app / "configmaps" / "backend-config.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: backend-config\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("KUBEOPTIX_DIAGRAM_EXCLUDE_PATH_REGEX", ".*/configmaps/.*")
    monkeypatch.setenv("KUBEOPTIX_DIAGRAM_INCLUDE_PATH_REGEX", ".*/configmaps/backend-config\\.yaml$")
    manifests = select_architecture_manifests(ns)
    names = {path.name for path in manifests}
    assert "backend-config.yaml" in names


def test_select_architecture_manifests_empty_for_missing_dir(tmp_path: Path) -> None:
    assert select_architecture_manifests(tmp_path / "missing") == ()


@pytest.mark.skipif(
    not TRAINING_NAMESPACE_ROOT.is_dir(),
    reason="Base de treinamento plfat-tbforte ausente",
)
def test_select_architecture_manifests_plfat_includes_routes() -> None:
    manifests = select_architecture_manifests(TRAINING_NAMESPACE_ROOT)
    names = {path.name for path in manifests}

    assert "agenda.yaml" in names
    assert any("deployments" in str(path) for path in manifests)
    assert any("services" in str(path) for path in manifests)
    assert len(manifests) >= 30
