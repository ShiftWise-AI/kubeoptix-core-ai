"""Testes de Events e upgrade de Operators (OLM)."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.events import analyze_events
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.analysis.inventory import analyze_inventory
from kubeoptix_core_ai.models.inventory import EventSpec, OperatorCSVSpec
from kubeoptix_core_ai.models.source import DataSourceRef
from kubeoptix_core_ai.models.workload import NamespaceWorkloadBundle
from kubeoptix_core_ai.parsers.csv import (
    catalog_keys_for_packagemanifest,
    packagemanifest_lookup_stems,
    parse_clusterserviceversion,
    parse_packagemanifest,
)
from kubeoptix_core_ai.parsers.event import parse_event

_SRC = DataSourceRef(file_path="/tmp/e.yaml", resource_kind="Event", resource_name="e")


def test_parse_event_warning(tmp_path: Path) -> None:
    path = tmp_path / "database.yaml"
    path.write_text(
        """apiVersion: v1
kind: Event
count: 12
involvedObject:
  kind: HorizontalPodAutoscaler
  name: database
  namespace: ns-test
message: 'failed to get cpu utilization: missing request for cpu'
metadata:
  name: database.abc
  namespace: ns-test
reason: FailedGetResourceMetric
type: Warning
""",
        encoding="utf-8",
    )
    event = parse_event(path)
    assert event.reason == "FailedGetResourceMetric"
    assert event.event_type == "Warning"
    assert event.count == 12
    assert event.involved_kind == "HorizontalPodAutoscaler"
    assert event.involved_name == "database"


def test_analyze_events_aggregates_warnings() -> None:
    events = (
        EventSpec(
            name="e1",
            namespace="ns-test",
            event_type="Warning",
            reason="Unhealthy",
            message="Readiness probe failed",
            count=25,
            involved_kind="Pod",
            involved_name="app-1",
            source=_SRC,
        ),
        EventSpec(
            name="e2",
            namespace="ns-test",
            event_type="Warning",
            reason="Unhealthy",
            message="Readiness probe failed",
            count=2,
            involved_kind="Pod",
            involved_name="app-1",
            source=_SRC,
        ),
        EventSpec(
            name="ok",
            namespace="ns-test",
            event_type="Normal",
            reason="Started",
            involved_kind="Pod",
            involved_name="app-1",
            source=_SRC,
        ),
    )
    ctx = AnalysisContext(
        bundle=NamespaceWorkloadBundle(namespace="ns-test", workloads=(), events=events),
        nodes=(),
    )
    builder = FindingBuilder()
    analyze_events(ctx, builder)
    findings = builder.findings
    assert len(findings) == 1
    assert findings[0].category == "EVENT"
    assert "Unhealthy" in findings[0].analysis
    assert "27" in findings[0].evidence[0].value


def test_kiali_packagemanifest_stems() -> None:
    stems = packagemanifest_lookup_stems({"kiali-operator", "cluster-logging"})
    assert "kiali-ossm" in stems
    assert "kiali-operator" in stems
    assert "cluster-logging" in stems
    keys = catalog_keys_for_packagemanifest("kiali-ossm", "kiali-operator.v2.27.2")
    assert "kiali-ossm" in keys
    assert "kiali-operator" in keys


def test_kiali_csv_maps_to_kiali_ossm_catalog(tmp_path: Path) -> None:
    csv_path = tmp_path / "kiali-operator.v2.22.2.yaml"
    csv_path.write_text(
        """apiVersion: operators.coreos.com/v1alpha1
kind: ClusterServiceVersion
metadata:
  name: kiali-operator.v2.22.2
spec:
  displayName: Kiali Operator
  version: 2.22.2
status:
  phase: Succeeded
  reason: Copied
""",
        encoding="utf-8",
    )
    pm_path = tmp_path / "kiali-ossm.yaml"
    pm_path.write_text(
        """apiVersion: packages.operators.coreos.com/v1
kind: PackageManifest
metadata:
  name: kiali-ossm
status:
  defaultChannel: stable
  channels:
  - name: stable
    currentCSV: kiali-operator.v2.27.2
""",
        encoding="utf-8",
    )
    op = parse_clusterserviceversion(csv_path)
    pkg, channel, current = parse_packagemanifest(pm_path)
    assert op.package_name == "kiali-operator"
    assert pkg == "kiali-ossm"
    assert current == "kiali-operator.v2.27.2"
    keys = catalog_keys_for_packagemanifest(pkg, current)
    assert op.package_name in keys
    assert current != op.name


def test_operator_upgrade_finding_per_csv() -> None:
    op = OperatorCSVSpec(
        name="devworkspace-operator.v0.37.0",
        display_name="DevWorkspace Operator",
        version="0.37.0",
        phase="Succeeded",
        reason="Copied",
        package_name="devworkspace-operator",
        default_channel="fast",
        channel_current_csv="devworkspace-operator.v0.42.0",
        upgrade_status="UpgradeAvailable",
        source=DataSourceRef(
            file_path="/tmp/csv.yaml",
            resource_kind="ClusterServiceVersion",
            resource_name="devworkspace-operator.v0.37.0",
        ),
    )
    ctx = AnalysisContext(
        bundle=NamespaceWorkloadBundle(
            namespace="ns-test",
            workloads=(),
            operators=(op,),
        ),
        nodes=(),
    )
    builder = FindingBuilder()
    analyze_inventory(ctx, builder)
    oper = [f for f in builder.findings if f.category == "OPER"]
    assert len(oper) == 1
    assert oper[0].severity.value == "MEDIUM"
    assert "Copied" in oper[0].analysis
    assert any("0.42.0" in item.value for item in oper[0].evidence)
