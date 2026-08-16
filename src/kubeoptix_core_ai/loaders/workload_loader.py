"""Carregador de workloads por namespace."""

from __future__ import annotations

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.discovery.scanner import discover_namespace
from kubeoptix_core_ai.errors import ConfigurationError, ParseError
from kubeoptix_core_ai.logging import get_logger
from kubeoptix_core_ai.models.inventory import (
    ConfigMapSpec,
    OperatorCSVSpec,
    PodLogSummary,
    RouteSpec,
    SecretReference,
    ServiceSpec,
)
from kubeoptix_core_ai.models.metrics import PodMetricsSnapshot
from kubeoptix_core_ai.models.workload import HPASpec, NamespaceWorkloadBundle, PodPlacement, Workload
from kubeoptix_core_ai.normalize.workload import enrich_workload
from kubeoptix_core_ai.parsers.configmap import parse_configmap
from kubeoptix_core_ai.parsers.csv import parse_clusterserviceversion, parse_packagemanifest
from kubeoptix_core_ai.parsers.deployment import parse_deployment
from kubeoptix_core_ai.parsers.hpa import parse_hpa
from kubeoptix_core_ai.parsers.log import parse_pod_log
from kubeoptix_core_ai.parsers.pod import parse_pod
from kubeoptix_core_ai.parsers.pod_metrics import parse_pod_metrics
from kubeoptix_core_ai.parsers.pvc import parse_pvc
from kubeoptix_core_ai.parsers.route import parse_route
from kubeoptix_core_ai.parsers.service import parse_service

logger = get_logger("loaders.workload")


class WorkloadLoader:
    """Carrega e normaliza workloads de um namespace."""

    def __init__(self, config: AnalyzerConfig | None = None) -> None:
        self._config = config or AnalyzerConfig.from_env()

    def load_namespace(self, namespace: str) -> NamespaceWorkloadBundle:
        """Carrega todos os workloads de um namespace."""
        namespace_root = self._config.namespace_path(namespace)
        if not namespace_root.is_dir():
            raise ConfigurationError(
                f"Diretório do namespace não encontrado: {namespace_root}"
            )

        paths = discover_namespace(namespace_root)
        parse_errors: list[str] = []
        skipped_files: list[str] = []
        processed_files: list[str] = []

        hpa_by_target: dict[str, HPASpec] = {}
        for hpa_file in paths.hpa_files:
            try:
                hpa = parse_hpa(hpa_file)
                processed_files.append(str(hpa_file))
                if hpa.target_workload_name:
                    hpa_by_target[hpa.target_workload_name] = hpa
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear HPA %s: %s", hpa_file, msg)

        placements_by_workload: dict[str, list[PodPlacement]] = {}
        qos_by_workload: dict[str, str] = {}
        for pod_file in paths.pod_files:
            try:
                placement = parse_pod(pod_file)
                processed_files.append(str(pod_file))
                workload_name = placement.workload_name or placement.pod_name
                placements_by_workload.setdefault(workload_name, []).append(placement)
                if placement.qos_class and workload_name not in qos_by_workload:
                    qos_by_workload[workload_name] = placement.qos_class
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear Pod %s: %s", pod_file, msg)

        metrics_by_workload: dict[str, list[PodMetricsSnapshot]] = {}
        for metrics_file in paths.pod_metrics_files:
            try:
                snapshot = parse_pod_metrics(metrics_file)
                processed_files.append(str(metrics_file))
                workload_key = _workload_name_from_pod(snapshot.pod_name)
                metrics_by_workload.setdefault(workload_key, []).append(snapshot)
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear PodMetrics %s: %s", metrics_file, msg)

        workloads: list[Workload] = []
        for deployment_file in paths.deployment_files:
            app_group = deployment_file.parent.parent.name
            try:
                workload = parse_deployment(deployment_file, app_group=app_group)
                processed_files.append(str(deployment_file))
                workload = workload.model_copy(
                    update={
                        "hpa": hpa_by_target.get(workload.name),
                        "placements": tuple(placements_by_workload.get(workload.name, ())),
                        "metrics": tuple(metrics_by_workload.get(workload.name, ())),
                        "qos_class": qos_by_workload.get(workload.name),
                    }
                )
                workloads.append(enrich_workload(workload))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning(
                    "Falha ao parsear Deployment %s: %s", deployment_file, msg
                )

        if not paths.deployment_files:
            logger.info("Nenhum Deployment encontrado em %s", namespace_root)

        pvcs: list = []
        pvc_dir = namespace_root / "resources" / "persistentvolumeclaims"
        if pvc_dir.is_dir():
            for pvc_file in sorted(pvc_dir.glob("*.yaml")):
                try:
                    pvcs.append(parse_pvc(pvc_file))
                    processed_files.append(str(pvc_file))
                except ParseError as exc:
                    msg = str(exc)
                    parse_errors.append(msg)
                    logger.warning("Falha ao parsear PVC %s: %s", pvc_file, msg)

        services, routes, configmaps, operators, pod_logs = _load_inventory_resources(
            paths, parse_errors, processed_files, logger
        )
        secret_references = _build_secret_references(workloads)

        return NamespaceWorkloadBundle(
            namespace=namespace,
            workloads=tuple(sorted(workloads, key=lambda w: w.name)),
            parse_errors=tuple(parse_errors),
            skipped_files=tuple(skipped_files),
            processed_files=tuple(sorted(processed_files)),
            pvcs=tuple(pvcs),
            services=services,
            routes=routes,
            configmaps=configmaps,
            operators=operators,
            pod_logs=pod_logs,
            secret_references=secret_references,
        )


def _load_inventory_resources(
    paths,
    parse_errors: list[str],
    processed_files: list[str],
    logger,
) -> tuple[
    tuple[ServiceSpec, ...],
    tuple[RouteSpec, ...],
    tuple[ConfigMapSpec, ...],
    tuple[OperatorCSVSpec, ...],
    tuple[PodLogSummary, ...],
]:
    services: list[ServiceSpec] = []
    for service_file in paths.service_files:
        try:
            services.append(parse_service(service_file))
            processed_files.append(str(service_file))
        except ParseError as exc:
            msg = str(exc)
            parse_errors.append(msg)
            logger.warning("Falha ao parsear Service %s: %s", service_file, msg)

    routes: list[RouteSpec] = []
    for route_file in paths.route_files:
        try:
            routes.append(parse_route(route_file))
            processed_files.append(str(route_file))
        except ParseError as exc:
            msg = str(exc)
            parse_errors.append(msg)
            logger.warning("Falha ao parsear Route %s: %s", route_file, msg)

    configmaps: list[ConfigMapSpec] = []
    for cm_file in paths.configmap_files:
        app_group = None
        if "apps" in cm_file.parts:
            try:
                apps_idx = cm_file.parts.index("apps")
                if apps_idx + 1 < len(cm_file.parts):
                    app_group = cm_file.parts[apps_idx + 1]
                    if app_group == "__sem_app__":
                        app_group = None
            except ValueError:
                pass
        try:
            configmaps.append(parse_configmap(cm_file, app_group=app_group))
            processed_files.append(str(cm_file))
        except ParseError as exc:
            msg = str(exc)
            parse_errors.append(msg)
            logger.warning("Falha ao parsear ConfigMap %s: %s", cm_file, msg)

    manifest_index: dict[str, tuple[str, str | None]] = {}
    package_names_needed: set[str] = set()

    operators: list[OperatorCSVSpec] = []
    for csv_file in paths.csv_files:
        try:
            op = parse_clusterserviceversion(csv_file)
            processed_files.append(str(csv_file))
            if op.package_name:
                package_names_needed.add(op.package_name)
            operators.append(op)
        except ParseError as exc:
            msg = str(exc)
            parse_errors.append(msg)
            logger.warning("Falha ao parsear CSV %s: %s", csv_file, msg)

    for pm_file in paths.packagemanifest_files:
        if pm_file.stem not in package_names_needed:
            continue
        try:
            pkg, channel, channel_csv = parse_packagemanifest(pm_file)
            manifest_index[pkg] = (channel, channel_csv)
            processed_files.append(str(pm_file))
        except ParseError as exc:
            msg = str(exc)
            parse_errors.append(msg)
            logger.warning("Falha ao parsear PackageManifest %s: %s", pm_file, msg)

    enriched: list[OperatorCSVSpec] = []
    for op in operators:
        if op.package_name and op.package_name in manifest_index:
            channel, channel_csv = manifest_index[op.package_name]
            upgrade = "Unknown"
            if channel_csv:
                upgrade = (
                    "AtLatestKnown" if op.name == channel_csv else "UpgradeAvailable"
                )
            op = op.model_copy(
                update={
                    "default_channel": channel or None,
                    "channel_current_csv": channel_csv,
                    "upgrade_status": upgrade,
                }
            )
        enriched.append(op)
    operators = enriched

    pod_logs: list[PodLogSummary] = []
    for log_file in paths.pod_log_files:
        app_group = log_file.parent.parent.name
        try:
            pod_logs.append(parse_pod_log(log_file, app_group=app_group))
            processed_files.append(str(log_file))
        except Exception as exc:  # noqa: BLE001 — log parsing não deve abortar carga
            msg = f"Falha ao parsear log {log_file}: {exc}"
            parse_errors.append(msg)
            logger.warning(msg)

    return (
        tuple(sorted(services, key=lambda s: s.name)),
        tuple(sorted(routes, key=lambda r: r.name)),
        tuple(sorted(configmaps, key=lambda c: c.name)),
        tuple(sorted(operators, key=lambda o: o.name)),
        tuple(sorted(pod_logs, key=lambda p: p.pod_name)),
    )


def _build_secret_references(workloads: list[Workload]) -> tuple[SecretReference, ...]:
    refs: list[SecretReference] = []
    for workload in workloads:
        pull_set = set(workload.image_pull_secrets)
        for name in workload.referenced_secrets:
            usage = "imagePullSecrets" if name in pull_set else "envFrom/volume"
            refs.append(
                SecretReference(
                    name=name,
                    usage=usage,
                    workload=workload.name,
                    source=workload.source,
                )
            )
        for name in workload.image_pull_secrets:
            if name not in workload.referenced_secrets:
                refs.append(
                    SecretReference(
                        name=name,
                        usage="imagePullSecrets",
                        workload=workload.name,
                        source=workload.source,
                    )
                )
    return tuple(sorted(refs, key=lambda r: (r.name, r.workload)))


def _workload_name_from_pod(pod_name: str) -> str:
    """
    Extrai nome provável do workload a partir do nome do pod.

    Padrão observado: <deployment>-<replicaset-hash>-<pod-suffix>
    """
    parts = pod_name.split("-")
    if len(parts) >= 3:
        return "-".join(parts[:-2])
    return pod_name
