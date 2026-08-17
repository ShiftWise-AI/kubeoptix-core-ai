"""Funções compartilhadas para parsing de controllers com pod template."""

from __future__ import annotations

from kubeoptix_core_ai.models.source import DataSourceRef, FieldRef
from kubeoptix_core_ai.models.storage import VolumeMountSpec, VolumeSpec
from kubeoptix_core_ai.models.workload import ContainerSpec, ProbeSpec
from kubeoptix_core_ai.normalize.quantities import parse_cpu_quantity, parse_memory_quantity


def field_ref(
    source: DataSourceRef,
    field_path: str,
    raw: str | int | float | None,
) -> FieldRef:
    return FieldRef(
        file_path=source.file_path,
        field_path=field_path,
        raw_value=str(raw) if raw is not None else None,
    )


def parse_probe(
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
        source=field_ref(source, base_path, None),
    )


def parse_container(
    container_data: dict,
    index: int,
    source: DataSourceRef,
    base_prefix: str = "spec.template.spec",
) -> ContainerSpec:
    name = str(container_data.get("name", f"container-{index}"))
    base = f"{base_prefix}.containers[{index}]"

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
            readiness_probe = parse_probe(probe, "readinessProbe", source, f"{base}.readinessProbe")
    if probe := container_data.get("livenessProbe"):
        if isinstance(probe, dict):
            liveness_probe = parse_probe(probe, "livenessProbe", source, f"{base}.livenessProbe")
    if probe := container_data.get("startupProbe"):
        if isinstance(probe, dict):
            startup_probe = parse_probe(probe, "startupProbe", source, f"{base}.startupProbe")

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


def parse_volumes(template_spec: dict, source: DataSourceRef, base_prefix: str) -> tuple[VolumeSpec, ...]:
    volumes: list[VolumeSpec] = []
    for idx, vol in enumerate(template_spec.get("volumes") or []):
        if not isinstance(vol, dict):
            continue
        name = str(vol.get("name", f"volume-{idx}"))
        base = f"{base_prefix}.volumes[{idx}]"
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
                source=field_ref(source, base, volume_type),
            )
        )
    return tuple(volumes)


def parse_volume_mounts(
    containers_data: list,
    source: DataSourceRef,
    base_prefix: str,
) -> tuple[VolumeMountSpec, ...]:
    mounts: list[VolumeMountSpec] = []
    for c_idx, container in enumerate(containers_data):
        if not isinstance(container, dict):
            continue
        c_name = str(container.get("name", f"container-{c_idx}"))
        for m_idx, mount in enumerate(container.get("volumeMounts") or []):
            if not isinstance(mount, dict):
                continue
            base = f"{base_prefix}.containers[{c_idx}].volumeMounts[{m_idx}]"
            mounts.append(
                VolumeMountSpec(
                    name=str(mount.get("name", "")),
                    mount_path=mount.get("mountPath"),
                    read_only=mount.get("readOnly"),
                    container_name=c_name,
                    source=field_ref(source, base, mount.get("mountPath")),
                )
            )
    return tuple(mounts)


def extract_resource_refs(
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
