"""Workload loader for a namespace."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from kubeoptix_core_ai.config import AnalyzerConfig
from kubeoptix_core_ai.discovery.scanner import discover_namespace, list_namespace_dirs
from kubeoptix_core_ai.errors import ConfigurationError, ParseError
from kubeoptix_core_ai.loaders.workload_correlation import (
    build_replicaset_index,
    correlate_autoscalers,
    correlate_metrics_by_workload,
    correlate_pdbs,
    correlate_pod_placements,
    enrich_workloads_with_correlations,
    filter_canonical_workloads,
)
from kubeoptix_core_ai.logging import get_logger
from kubeoptix_core_ai.models.inventory import (
    ConfigMapSpec,
    EventSpec,
    OperatorCSVSpec,
    PodLogSummary,
    RouteSpec,
    SecretReference,
    ServiceSpec,
)
from kubeoptix_core_ai.models.metrics import PodMetricsSnapshot
from kubeoptix_core_ai.models.workload import (
    HPASpec,
    NamespaceWorkloadBundle,
    PDBSpec,
    PodPlacement,
    VPASpec,
    Workload,
)
from kubeoptix_core_ai.normalize.ownership import (
    resolve_workload_from_owner,
    workload_name_from_pod,
)
from kubeoptix_core_ai.normalize.workload import enrich_workload
from kubeoptix_core_ai.parsers.configmap import parse_configmap
from kubeoptix_core_ai.parsers.csv import (
    catalog_keys_for_packagemanifest,
    packagemanifest_lookup_stems,
    parse_clusterserviceversion,
    parse_packagemanifest,
)
from kubeoptix_core_ai.parsers.event import parse_event
from kubeoptix_core_ai.parsers.hpa import parse_hpa
from kubeoptix_core_ai.parsers.log import parse_pod_log
from kubeoptix_core_ai.parsers.pdb import parse_pdb
from kubeoptix_core_ai.parsers.pod import parse_pod
from kubeoptix_core_ai.parsers.pod_metrics import parse_pod_metrics
from kubeoptix_core_ai.parsers.pvc import parse_pvc
from kubeoptix_core_ai.parsers.route import parse_route
from kubeoptix_core_ai.parsers.service import parse_service
from kubeoptix_core_ai.parsers.vpa import parse_vpa
from kubeoptix_core_ai.parsers.workload_controller import parse_workload_controller

logger = get_logger("loaders.workload")

_TRACKED_PATH_ATTRS = frozenset(
    {
        "workload_files",
        "pod_files",
        "pod_metrics_files",
        "hpa_files",
        "vpa_files",
        "pdb_files",
        "pvc_files",
        "service_files",
        "route_files",
        "configmap_files",
        "csv_files",
        "packagemanifest_files",
        "event_files",
        "pod_log_files",
    }
)


class _TrackingNamespacePaths:
    """Iterate namespace files and report progress after each one."""

    def __init__(
        self,
        paths,
        on_file_processed: Callable[[int, int], None],
        on_file_started: Callable[[Path], None] | None = None,
    ) -> None:
        self._paths = paths
        self._on_file_processed = on_file_processed
        self._on_file_started = on_file_started
        self._attempted = 0
        self._total = paths.processable_file_count

    def __getattr__(self, name: str):
        value = getattr(self._paths, name)
        if name in _TRACKED_PATH_ATTRS:
            return self._tracked(value)
        return value

    def _tracked(self, files):
        for item in files:
            if self._on_file_started is not None:
                self._on_file_started(item)
            yield item
            self._attempted += 1
            self._on_file_processed(self._attempted, self._total)


class WorkloadLoader:
    """Load and normalize workloads for a namespace."""

    def __init__(self, config: AnalyzerConfig | None = None) -> None:
        self._config = config or AnalyzerConfig.from_env()

    def load_namespace(
        self,
        namespace: str,
        *,
        on_file_processed: Callable[[int, int], None] | None = None,
        on_file_started: Callable[[Path], None] | None = None,
        include_olm: bool = True,
        include_events: bool = True,
        include_logs: bool = True,
        include_inventory: bool = True,
    ) -> NamespaceWorkloadBundle:
        """Load all workloads from a namespace."""
        namespace_root = self._config.namespace_path(namespace)
        if not namespace_root.is_dir():
            raise ConfigurationError(
                f"Diretório do namespace não encontrado: {namespace_root}"
            )

        paths = discover_namespace(namespace_root)
        parse_errors: list[str] = []
        skipped_files: list[str] = []
        processed_files: list[str] = []
        if on_file_processed is not None:
            paths = _TrackingNamespacePaths(
                paths,
                on_file_processed,
                on_file_started=on_file_started,
            )

        raw_workloads = self._load_workload_controllers(
            paths, parse_errors, processed_files
        )
        rs_index = build_replicaset_index(raw_workloads)

        hpas, vpas, pdbs = self._load_operational_resources(
            paths, parse_errors, processed_files
        )
        hpa_by_target, vpa_by_target = correlate_autoscalers(hpas, vpas)

        placements, qos_by_workload = self._load_pods(
            paths, rs_index, parse_errors, processed_files
        )
        placements_by_workload = correlate_pod_placements(placements)

        metrics_by_workload = self._load_pod_metrics(
            paths, placements, parse_errors, processed_files
        )

        canonical = filter_canonical_workloads(raw_workloads)
        pdb_by_workload = correlate_pdbs(pdbs, canonical)

        workloads = enrich_workloads_with_correlations(
            canonical,
            placements_by_workload,
            metrics_by_workload,
            qos_by_workload,
            hpa_by_target,
            vpa_by_target,
            pdb_by_workload,
        )
        workloads = [enrich_workload(w) for w in workloads]

        if not canonical and not raw_workloads:
            logger.info("Nenhum workload controller encontrado em %s", namespace_root)

        pvcs = self._load_pvcs(paths, parse_errors, processed_files)
        services, routes, configmaps, operators, events, pod_logs = (
            _load_inventory_resources(
                paths,
                parse_errors,
                processed_files,
                logger,
                include_olm=include_olm,
                include_events=include_events,
                include_logs=include_logs,
                include_inventory=include_inventory,
            )
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
            events=events,
            pod_logs=pod_logs,
            secret_references=secret_references,
        )

    def load_fleet_workloads(self) -> tuple[Workload, ...]:
        """Load workloads from all namespaces for fleet baseline.

        Omits OLM catalog entries, events, and logs — only controllers, pods, and metrics.
        """
        workloads: list[Workload] = []
        for ns_dir in list_namespace_dirs(self._config.workloads_base):
            try:
                bundle = self.load_namespace(
                    ns_dir.name,
                    include_olm=False,
                    include_events=False,
                    include_logs=False,
                    include_inventory=False,
                )
            except ConfigurationError:
                continue
            workloads.extend(bundle.workloads)
        return tuple(workloads)

    def _load_workload_controllers(
        self,
        paths,
        parse_errors: list[str],
        processed_files: list[str],
    ) -> list[Workload]:
        workloads: list[Workload] = []
        for workload_file in paths.workload_files:
            app_group = _app_group_from_path(workload_file)
            try:
                workload = parse_workload_controller(workload_file, app_group=app_group)
                processed_files.append(str(workload_file))
                workloads.append(workload)
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning(
                    "Falha ao parsear workload %s: %s", workload_file, msg
                )
        return workloads

    def _load_operational_resources(
        self,
        paths,
        parse_errors: list[str],
        processed_files: list[str],
    ) -> tuple[list[HPASpec], list[VPASpec], list[PDBSpec]]:
        hpas: list[HPASpec] = []
        for hpa_file in paths.hpa_files:
            try:
                hpas.append(parse_hpa(hpa_file))
                processed_files.append(str(hpa_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear HPA %s: %s", hpa_file, msg)

        vpas: list[VPASpec] = []
        for vpa_file in paths.vpa_files:
            try:
                vpas.append(parse_vpa(vpa_file))
                processed_files.append(str(vpa_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear VPA %s: %s", vpa_file, msg)

        pdbs: list[PDBSpec] = []
        for pdb_file in paths.pdb_files:
            try:
                pdbs.append(parse_pdb(pdb_file))
                processed_files.append(str(pdb_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear PDB %s: %s", pdb_file, msg)

        return hpas, vpas, pdbs

    def _load_pods(
        self,
        paths,
        rs_index,
        parse_errors: list[str],
        processed_files: list[str],
    ) -> tuple[list[PodPlacement], dict[str, str]]:
        placements: list[PodPlacement] = []
        qos_by_workload: dict[str, str] = {}

        for pod_file in paths.pod_files:
            try:
                placement = parse_pod(pod_file)
                processed_files.append(str(pod_file))

                workload_name = placement.workload_name
                if workload_name is None:
                    workload_name = _resolve_pod_workload_from_file(pod_file, rs_index)

                if workload_name:
                    placement = placement.model_copy(update={"workload_name": workload_name})

                placements.append(placement)
                if placement.qos_class and workload_name and workload_name not in qos_by_workload:
                    qos_by_workload[workload_name] = placement.qos_class
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear Pod %s: %s", pod_file, msg)

        return placements, qos_by_workload

    def _load_pod_metrics(
        self,
        paths,
        placements: list[PodPlacement],
        parse_errors: list[str],
        processed_files: list[str],
    ) -> dict[str, list[PodMetricsSnapshot]]:
        metrics_by_pod: dict[str, list[PodMetricsSnapshot]] = {}
        for metrics_file in paths.pod_metrics_files:
            try:
                snapshot = parse_pod_metrics(metrics_file)
                processed_files.append(str(metrics_file))
                metrics_by_pod.setdefault(snapshot.pod_name, []).append(snapshot)
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear PodMetrics %s: %s", metrics_file, msg)

        return correlate_metrics_by_workload(metrics_by_pod, placements)

    def _load_pvcs(
        self,
        paths,
        parse_errors: list[str],
        processed_files: list[str],
    ) -> list:
        pvcs: list = []
        for pvc_file in paths.pvc_files:
            try:
                pvcs.append(parse_pvc(pvc_file))
                processed_files.append(str(pvc_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear PVC %s: %s", pvc_file, msg)
        return pvcs


def _app_group_from_path(file_path: Path) -> str | None:
    parts = file_path.parts
    if "apps" in parts:
        try:
            apps_idx = parts.index("apps")
            if apps_idx + 1 < len(parts):
                app_group = parts[apps_idx + 1]
                if app_group != "__sem_app__":
                    return app_group
        except ValueError:
            pass
    return None


def _resolve_pod_workload_from_file(pod_file: Path, rs_index) -> str | None:
    """Re-parse ownerReferences com índice de ReplicaSets para correlação."""
    from kubeoptix_core_ai.parsers.base import load_yaml_file

    try:
        document = load_yaml_file(pod_file)
    except ParseError:
        return None

    metadata = document.get("metadata") or {}
    pod_name = str(metadata.get("name", pod_file.stem))

    for owner in metadata.get("ownerReferences") or []:
        if not isinstance(owner, dict):
            continue
        kind = str(owner.get("kind", ""))
        name = str(owner.get("name", ""))
        if not kind or not name:
            continue
        resolved = resolve_workload_from_owner(kind, name, rs_index)
        if resolved:
            return resolved[0]

    return workload_name_from_pod(pod_name)


def _load_inventory_resources(
    paths,
    parse_errors: list[str],
    processed_files: list[str],
    logger,
    *,
    include_olm: bool = True,
    include_events: bool = True,
    include_logs: bool = True,
    include_inventory: bool = True,
) -> tuple[
    tuple[ServiceSpec, ...],
    tuple[RouteSpec, ...],
    tuple[ConfigMapSpec, ...],
    tuple[OperatorCSVSpec, ...],
    tuple[EventSpec, ...],
    tuple[PodLogSummary, ...],
]:
    services: list[ServiceSpec] = []
    routes: list[RouteSpec] = []
    configmaps: list[ConfigMapSpec] = []
    if include_inventory:
        for service_file in paths.service_files:
            try:
                services.append(parse_service(service_file))
                processed_files.append(str(service_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear Service %s: %s", service_file, msg)

        for route_file in paths.route_files:
            try:
                routes.append(parse_route(route_file))
                processed_files.append(str(route_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear Route %s: %s", route_file, msg)

        for cm_file in paths.configmap_files:
            app_group = _app_group_from_path(cm_file)
            try:
                configmaps.append(parse_configmap(cm_file, app_group=app_group))
                processed_files.append(str(cm_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear ConfigMap %s: %s", cm_file, msg)

    manifest_index: dict[str, tuple[str, str, str | None]] = {}
    package_names_needed: set[str] = set()

    operators: list[OperatorCSVSpec] = []
    if include_olm:
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

        needed_stems = packagemanifest_lookup_stems(package_names_needed)
        for pm_file in paths.packagemanifest_files:
            if pm_file.stem not in needed_stems:
                continue
            try:
                pkg, channel, channel_csv = parse_packagemanifest(pm_file)
                entry = (pkg, channel, channel_csv)
                for key in catalog_keys_for_packagemanifest(pkg, channel_csv):
                    manifest_index[key] = entry
                processed_files.append(str(pm_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear PackageManifest %s: %s", pm_file, msg)

    enriched: list[OperatorCSVSpec] = []
    for op in operators:
        catalog = None
        if op.package_name:
            catalog = manifest_index.get(op.package_name)
        if catalog is None:
            catalog = manifest_index.get(op.name)
        if catalog is not None:
            pkg, channel, channel_csv = catalog
            upgrade = "Unknown"
            if channel_csv:
                upgrade = (
                    "AtLatestKnown" if op.name == channel_csv else "UpgradeAvailable"
                )
            op = op.model_copy(
                update={
                    "package_name": pkg or op.package_name,
                    "default_channel": channel or None,
                    "channel_current_csv": channel_csv,
                    "upgrade_status": upgrade,
                }
            )
        enriched.append(op)
    operators = enriched

    events: list[EventSpec] = []
    if include_events:
        for event_file in paths.event_files:
            try:
                events.append(parse_event(event_file))
                processed_files.append(str(event_file))
            except ParseError as exc:
                msg = str(exc)
                parse_errors.append(msg)
                logger.warning("Falha ao parsear Event %s: %s", event_file, msg)

    pod_logs: list[PodLogSummary] = []
    if include_logs:
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
        tuple(sorted(events, key=lambda e: e.name)),
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
