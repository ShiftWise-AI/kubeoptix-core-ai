"""Parser de Deployments (apps/v1)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.errors import ParseError
from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef, source_from_document
from kubeoptix_core_ai.models.storage import VolumeMountSpec, VolumeSpec
from kubeoptix_core_ai.models.workload import ContainerSpec, ProbeSpec, Workload
from kubeoptix_core_ai.normalize.quantities import parse_cpu_quantity, parse_memory_quantity
from kubeoptix_core_ai.parsers.base import load_yaml_file


def _field_ref(source: DataSourceRef, field_path: str, raw: str | int | float | None) -> FieldRef:
    return FieldRef(
        file_path=source.file_path,
        field_path=field_path,
        raw_value=str(raw) if raw is not None else None,
    )


def _parse_probe(
    probe_data: dict,
    probe_type: str,
    source: DataSourceRef,
    base_path: str,
) -> ProbeSpec:
    handler_type = None
    path = None
    port: int | str | None = None

    if "httpGet" in probe_data:
        handler_type = "httpGet"
        http_get = probe_data["httpGet"]
        path = http_get.get("path")
        port = http_get.get("port")
    elif "tcpSocket" in probe_data:
        handler_type = "tcpSocket"
        port = probe_data["tcpSocket"].get("port")
    elif "exec" in probe_data:
        handler_type = "exec"

    return ProbeSpec(
        probe_type=probe_type,
        handler_type=handler_type,
        path=path,
        port=port,
        source=_field_ref(source, base_path, None),
    )


def _parse_container(
    container_data: dict,
    index: int,
    source: DataSourceRef,
) -> ContainerSpec:
    name = str(container_data.get("name", f"container-{index}"))
    base = f"spec.template.spec.containers[{index}]"

    resources = container_data.get("resources") or {}
    requests = resources.get("requests") or {}
    limits = resources.get("limits") or {}

    cpu_request = None
    cpu_limit = None
    memory_request = None
    memory_limit = None

    if "cpu" in requests:
        cpu_request = parse_cpu_quantity(
            requests["cpu"],
            source=source,
            field_path=f"{base}.resources.requests.cpu",
        )
    if "cpu" in limits:
        cpu_limit = parse_cpu_quantity(
            limits["cpu"],
            source=source,
            field_path=f"{base}.resources.limits.cpu",
        )
    if "memory" in requests:
        memory_request = parse_memory_quantity(
            requests["memory"],
            source=source,
            field_path=f"{base}.resources.requests.memory",
        )
    if "memory" in limits:
        memory_limit = parse_memory_quantity(
            limits["memory"],
            source=source,
            field_path=f"{base}.resources.limits.memory",
        )

    readiness_probe = None
    liveness_probe = None
    startup_probe = None

    if probe := container_data.get("readinessProbe"):
        if isinstance(probe, dict):
            readiness_probe = _parse_probe(probe, "readinessProbe", source, f"{base}.readinessProbe")
    if probe := container_data.get("livenessProbe"):
        if isinstance(probe, dict):
            liveness_probe = _parse_probe(probe, "livenessProbe", source, f"{base}.livenessProbe")
    if probe := container_data.get("startupProbe"):
        if isinstance(probe, dict):
            startup_probe = _parse_probe(probe, "startupProbe", source, f"{base}.startupProbe")

    image = container_data.get("image")
    if image is not None:
        image = str(image)

    return ContainerSpec(
        name=name,
        image=image,
        cpu_request=cpu_request,
        cpu_limit=cpu_limit,
        memory_request=memory_request,
        memory_limit=memory_limit,
        readiness_probe=readiness_probe,
        liveness_probe=liveness_probe,
        startup_probe=startup_probe,
        source=DataSourceRef(
            file_path=source.file_path,
            resource_kind=source.resource_kind,
            resource_name=source.resource_name,
            namespace=source.namespace,
        ),
    )


def _parse_volumes(
    template_spec: dict,
    source: DataSourceRef,
) -> tuple[VolumeSpec, ...]:
    volumes: list[VolumeSpec] = []
    for idx, vol in enumerate(template_spec.get("volumes") or []):
        if not isinstance(vol, dict):
            continue
        name = str(vol.get("name", f"volume-{idx}"))
        base = f"spec.template.spec.volumes[{idx}]"
        volume_type = "unknown"
        claim_name = None

        if "persistentVolumeClaim" in vol:
            volume_type = "persistentVolumeClaim"
            pvc = vol["persistentVolumeClaim"]
            if isinstance(pvc, dict):
                claim_name = pvc.get("claimName")
                if claim_name is not None:
                    claim_name = str(claim_name)
        elif "emptyDir" in vol:
            volume_type = "emptyDir"
        elif "configMap" in vol:
            volume_type = "configMap"
        elif "secret" in vol:
            volume_type = "secret"
        elif "projected" in vol:
            volume_type = "projected"

        volumes.append(
            VolumeSpec(
                name=name,
                volume_type=volume_type,
                claim_name=claim_name,
                source=_field_ref(source, base, volume_type),
            )
        )
    return tuple(volumes)


def _parse_volume_mounts(
    containers_data: list,
    source: DataSourceRef,
) -> tuple[VolumeMountSpec, ...]:
    mounts: list[VolumeMountSpec] = []
    for c_idx, container in enumerate(containers_data):
        if not isinstance(container, dict):
            continue
        c_name = str(container.get("name", f"container-{c_idx}"))
        for m_idx, mount in enumerate(container.get("volumeMounts") or []):
            if not isinstance(mount, dict):
                continue
            base = f"spec.template.spec.containers[{c_idx}].volumeMounts[{m_idx}]"
            mounts.append(
                VolumeMountSpec(
                    name=str(mount.get("name", "")),
                    mount_path=mount.get("mountPath"),
                    read_only=mount.get("readOnly"),
                    container_name=c_name,
                    source=_field_ref(source, base, mount.get("mountPath")),
                )
            )
    return tuple(mounts)


def _extract_resource_refs(
    template_spec: dict,
    containers_data: list,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    configmaps: set[str] = set()
    secrets: set[str] = set()
    pull_secrets: set[str] = set()

    for ips in template_spec.get("imagePullSecrets") or []:
        if isinstance(ips, dict) and ips.get("name"):
            pull_secrets.add(str(ips["name"]))
            secrets.add(str(ips["name"]))

    for vol in template_spec.get("volumes") or []:
        if not isinstance(vol, dict):
            continue
        if "configMap" in vol and isinstance(vol["configMap"], dict):
            name = vol["configMap"].get("name")
            if name:
                configmaps.add(str(name))
        if "secret" in vol and isinstance(vol["secret"], dict):
            name = vol["secret"].get("secretName")
            if name:
                secrets.add(str(name))

    for container in containers_data:
        if not isinstance(container, dict):
            continue
        for env_from in container.get("envFrom") or []:
            if not isinstance(env_from, dict):
                continue
            if "configMapRef" in env_from and isinstance(env_from["configMapRef"], dict):
                name = env_from["configMapRef"].get("name")
                if name:
                    configmaps.add(str(name))
            if "secretRef" in env_from and isinstance(env_from["secretRef"], dict):
                name = env_from["secretRef"].get("name")
                if name:
                    secrets.add(str(name))
        for env in container.get("env") or []:
            if not isinstance(env, dict):
                continue
            value_from = env.get("valueFrom")
            if not isinstance(value_from, dict):
                continue
            if "configMapKeyRef" in value_from:
                ref = value_from["configMapKeyRef"]
                if isinstance(ref, dict) and ref.get("name"):
                    configmaps.add(str(ref["name"]))
            if "secretKeyRef" in value_from:
                ref = value_from["secretKeyRef"]
                if isinstance(ref, dict) and ref.get("name"):
                    secrets.add(str(ref["name"]))

    return (
        tuple(sorted(configmaps)),
        tuple(sorted(secrets)),
        tuple(sorted(pull_secrets)),
    )


def parse_deployment(file_path: Path, *, app_group: str | None = None) -> Workload:
    """Interpreta um arquivo YAML de Deployment."""
    document = load_yaml_file(file_path)
    kind = document.get("kind")
    if kind != "Deployment":
        raise ParseError(
            f"kind esperado 'Deployment', encontrado {kind!r}",
            file_path=file_path,
        )

    source = source_from_document(file_path, document)
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    status = document.get("status") or {}
    template_spec = (spec.get("template") or {}).get("spec") or {}

    namespace = str(metadata.get("namespace", ""))
    name = str(metadata.get("name", file_path.stem))
    group = app_group or name

    containers_data = template_spec.get("containers") or []
    if not isinstance(containers_data, list):
        raise ParseError("spec.template.spec.containers deve ser uma lista", file_path=file_path)

    containers = tuple(
        _parse_container(container, idx, source)
        for idx, container in enumerate(containers_data)
        if isinstance(container, dict)
    )

    node_selector = template_spec.get("nodeSelector") or {}
    if not isinstance(node_selector, dict):
        node_selector = {}

    node_selector_normalized = {str(k): str(v) for k, v in node_selector.items()}

    match_labels_raw = spec.get("selector", {}).get("matchLabels") or {}
    if not isinstance(match_labels_raw, dict):
        match_labels_raw = {}
    match_labels = {str(k): str(v) for k, v in match_labels_raw.items()}

    template_metadata = (spec.get("template") or {}).get("metadata") or {}
    pod_labels_raw = template_metadata.get("labels") or {}
    if not isinstance(pod_labels_raw, dict):
        pod_labels_raw = {}
    pod_template_labels = {str(k): str(v) for k, v in pod_labels_raw.items()}

    affinity = template_spec.get("affinity")
    tolerations = template_spec.get("tolerations")
    topology = template_spec.get("topologySpreadConstraints")

    replicas_desired = spec.get("replicas")
    if replicas_desired is not None:
        replicas_desired = int(replicas_desired)

    replicas_ready = status.get("readyReplicas")
    if replicas_ready is not None:
        replicas_ready = int(replicas_ready)

    replicas_available = status.get("availableReplicas")
    if replicas_available is not None:
        replicas_available = int(replicas_available)

    volumes = _parse_volumes(template_spec, source)
    volume_mounts = _parse_volume_mounts(containers_data, source)
    referenced_configmaps, referenced_secrets, image_pull_secrets = _extract_resource_refs(
        template_spec, containers_data
    )

    return Workload(
        namespace=namespace,
        name=name,
        app_group=group,
        kind="Deployment",
        replicas_desired=replicas_desired,
        replicas_ready=replicas_ready,
        replicas_available=replicas_available,
        containers=containers,
        node_selector=node_selector_normalized,
        pod_template_labels=pod_template_labels,
        match_labels=match_labels,
        affinity=affinity if isinstance(affinity, dict) else None,
        tolerations=tolerations if isinstance(tolerations, list) else None,
        topology_spread_constraints=topology if isinstance(topology, list) else None,
        volumes=volumes,
        volume_mounts=volume_mounts,
        referenced_configmaps=referenced_configmaps,
        referenced_secrets=referenced_secrets,
        image_pull_secrets=image_pull_secrets,
        source=source,
    )
