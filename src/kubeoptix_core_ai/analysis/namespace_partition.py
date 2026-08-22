"""Proposta de quebra de namespace com base em comunicação e dependências."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.analysis.workload_refs import extract_service_calls
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity
from kubeoptix_core_ai.models.inventory import RouteSpec, ServiceSpec
from kubeoptix_core_ai.models.workload import Workload
from kubeoptix_core_ai.visualization.topology.matcher import workloads_for_service

MIN_WORKLOADS_FOR_SPLIT = 6
MIN_GROUPS_FOR_SPLIT = 2
MAX_ARCHITECTURE_DIAGRAMS = 6
_PLATFORM_CONFIGMAPS = frozenset({"kube-root-ca.crt", "openshift-service-ca.crt"})
_PLATFORM_SECRET_MARKERS = ("-token-", "-dockercfg", "-token")
_JOB_KINDS = frozenset({"Job", "CronJob"})
_STATEFUL_KINDS = frozenset({"StatefulSet"})


@dataclass(frozen=True)
class CouplingEdge:
    left: str
    right: str
    kind: str
    detail: str
    weight: int


@dataclass(frozen=True)
class ProposedNamespace:
    suggested_name: str
    slug: str
    role: str
    workload_names: tuple[str, ...]
    rationale: str
    app_groups: tuple[str, ...] = ()
    outbound_to: tuple[str, ...] = ()
    inbound_from: tuple[str, ...] = ()
    residual_calls: tuple[str, ...] = ()


@dataclass(frozen=True)
class NamespacePartition:
    current_namespace: str
    workload_count: int
    groups: tuple[ProposedNamespace, ...]
    edges: tuple[CouplingEdge, ...]
    should_split: bool
    skip_reason: str | None = None


class _UnionFind:
    def __init__(self, items: tuple[str, ...]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        parent = self._parent[item]
        if parent != item:
            self._parent[item] = self.find(parent)
        return self._parent[item]

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self._parent[root_right] = root_left


def _dns_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "app"


def _common_name_prefix(names: tuple[str, ...]) -> str | None:
    if len(names) < 2:
        return None
    prefix = names[0]
    for name in names[1:]:
        limit = min(len(prefix), len(name))
        i = 0
        while i < limit and prefix[i] == name[i]:
            i += 1
        prefix = prefix[:i]
        if len(prefix) < 3:
            return None
    prefix = prefix.rstrip("-")
    if len(prefix) < 3:
        return None
    return prefix


def _is_platform_config(name: str) -> bool:
    if name in _PLATFORM_CONFIGMAPS:
        return True
    lower = name.lower()
    return any(marker in lower for marker in _PLATFORM_SECRET_MARKERS)


def _shared_resource_is_platform(users: int, workload_count: int) -> bool:
    if users <= 1:
        return True
    if users >= max(4, int(workload_count * 0.4)):
        return True
    return False


def _app_key(workload: Workload) -> str:
    group = workload.app_group or workload.name
    if group == "__sem_app__":
        return workload.name
    return group


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)
    return (left, right) if left <= right else (right, left)


def _workload_role(workloads: tuple[Workload, ...], routed: set[str]) -> str:
    kinds = {wl.kind for wl in workloads}
    names = {wl.name for wl in workloads}
    if names & routed:
        return "exposição HTTP"
    if kinds <= _JOB_KINDS:
        return "processamento em lote"
    if kinds & _STATEFUL_KINDS:
        return "dados / stateful"
    return "API / serviços internos"


def _group_slug(
    workloads: tuple[Workload, ...],
    role: str,
    used: set[str],
) -> str:
    names = tuple(sorted(wl.name for wl in workloads))
    app_groups = {wl.app_group for wl in workloads if wl.app_group}
    prefix = _common_name_prefix(names)
    role_slugs = {
        "exposição HTTP": "frontend",
        "processamento em lote": "jobs",
        "dados / stateful": "data",
        "API / serviços internos": "api",
    }
    candidates = []
    if len(app_groups) == 1:
        group = next(iter(app_groups))
        if group and group != "__sem_app__":
            candidates.append(_dns_slug(group))
    if prefix:
        candidates.append(_dns_slug(prefix))
    candidates.append(role_slugs.get(role, "app"))
    for candidate in candidates:
        if candidate not in used:
            return candidate
    index = 2
    base = candidates[0]
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"


def _suggested_name(current: str, slug: str) -> str:
    name = f"{current}-{slug}"
    return name[:63].rstrip("-")


def _rationale(
    workloads: tuple[Workload, ...],
    edges: tuple[CouplingEdge, ...],
    role: str,
) -> str:
    names = {wl.name for wl in workloads}
    internal = [
        edge
        for edge in edges
        if edge.left in names and edge.right in names
    ]
    kinds = sorted({edge.kind for edge in internal})
    if internal:
        return (
            f"{len(workloads)} workload(s) com papel de {role}; "
            f"acoplados por {', '.join(kinds)}."
        )
    app_groups = sorted({wl.app_group for wl in workloads if wl.app_group})
    if len(app_groups) == 1 and app_groups[0] != "__sem_app__":
        return (
            f"{len(workloads)} workload(s) do grupo `{app_groups[0]}` sem "
            "chamadas de Service evidenciadas entre si."
        )
    return f"{len(workloads)} workload(s) com papel de {role}."


def build_coupling_edges(
    workloads: tuple[Workload, ...],
    services: tuple[ServiceSpec, ...],
) -> tuple[CouplingEdge, ...]:
    """Arestas de acoplamento comprováveis (selector, env, PVC, Secret/CM dedicado)."""
    if not workloads:
        return ()

    by_name = {wl.name: wl for wl in workloads}
    service_names = {svc.name for svc in services}
    edges: list[CouplingEdge] = []
    seen: set[tuple[str, str, str, str]] = set()

    def _add(left: str, right: str, kind: str, detail: str, weight: int) -> None:
        if left == right or left not in by_name or right not in by_name:
            return
        a, b = _pair_key(left, right)
        key = (a, b, kind, detail)
        if key in seen:
            return
        seen.add(key)
        edges.append(CouplingEdge(left=a, right=b, kind=kind, detail=detail, weight=weight))

    for service in services:
        selected = workloads_for_service(service, workloads)
        selected_names = [wl.name for wl in selected]
        for index, left in enumerate(selected_names):
            for right in selected_names[index + 1 :]:
                _add(left, right, "service_selector", f"Service/{service.name}", 3)

    service_by_name = {svc.name: svc for svc in services}
    for workload in workloads:
        for service_name, _field, env_name in extract_service_calls(workload, service_names):
            detail = (
                f"env {env_name} → Service/{service_name}"
                if env_name
                else f"Service/{service_name}"
            )
            service = service_by_name.get(service_name)
            if service is None:
                continue
            for target in workloads_for_service(service, workloads):
                _add(workload.name, target.name, "env_call", detail, 3)

    pvc_owners: dict[str, list[str]] = defaultdict(list)
    secret_owners: dict[str, list[str]] = defaultdict(list)
    cm_owners: dict[str, list[str]] = defaultdict(list)
    for workload in workloads:
        for volume in workload.volumes:
            if volume.claim_name:
                pvc_owners[volume.claim_name].append(workload.name)
        for secret in workload.referenced_secrets:
            if not _is_platform_config(secret):
                secret_owners[secret].append(workload.name)
        for configmap in workload.referenced_configmaps:
            if not _is_platform_config(configmap):
                cm_owners[configmap].append(workload.name)

    workload_count = len(workloads)
    for claim, owners in pvc_owners.items():
        unique = tuple(sorted(set(owners)))
        if len(unique) < 2:
            continue
        for index, left in enumerate(unique):
            for right in unique[index + 1 :]:
                _add(left, right, "shared_pvc", f"PVC/{claim}", 3)

    for resource_kind, owners_map in (
        ("shared_secret", secret_owners),
        ("shared_configmap", cm_owners),
    ):
        for resource_name, owners in owners_map.items():
            unique = tuple(sorted(set(owners)))
            if _shared_resource_is_platform(len(unique), workload_count):
                continue
            label = "Secret" if resource_kind == "shared_secret" else "ConfigMap"
            for index, left in enumerate(unique):
                for right in unique[index + 1 :]:
                    _add(
                        left,
                        right,
                        resource_kind,
                        f"{label}/{resource_name}",
                        2,
                    )

    return tuple(edges)


def propose_namespace_partition(
    namespace: str,
    workloads: tuple[Workload, ...],
    services: tuple[ServiceSpec, ...] = (),
    routes: tuple[RouteSpec, ...] = (),
    *,
    min_workloads: int = MIN_WORKLOADS_FOR_SPLIT,
) -> NamespacePartition:
    """Agrupa workloads por aplicação e une grupos só com comunicação comprovável."""
    workload_count = len(workloads)
    if workload_count < min_workloads:
        return NamespacePartition(
            current_namespace=namespace,
            workload_count=workload_count,
            groups=(),
            edges=(),
            should_split=False,
            skip_reason=(
                f"O namespace tem {workload_count} workload(s); a redistribuição "
                f"só é sugerida a partir de {min_workloads} workloads."
            ),
        )

    edges = build_coupling_edges(workloads, services)
    app_keys = tuple(sorted({_app_key(wl) for wl in workloads}))
    union = _UnionFind(app_keys)
    name_to_app = {wl.name: _app_key(wl) for wl in workloads}
    for edge in edges:
        if edge.weight >= 2:
            union.union(name_to_app[edge.left], name_to_app[edge.right])

    buckets: dict[str, list[str]] = defaultdict(list)
    for workload in workloads:
        buckets[union.find(name_to_app[workload.name])].append(workload.name)
    grouped = [sorted(members) for members in buckets.values()]
    grouped.sort(key=lambda members: (-len(members), members[0]))

    by_name = {wl.name: wl for wl in workloads}
    should_split = len(grouped) >= MIN_GROUPS_FOR_SPLIT
    skip_reason = None
    if not should_split:
        skip_reason = (
            "Os grupos de aplicação formam um único conjunto acoplado por "
            "comunicação ou dependências evidenciadas nos YAMLs."
        )

    routed_workloads: set[str] = set()
    service_map = {svc.name: svc for svc in services}
    for route in routes:
        target = service_map.get(route.target_service or "")
        if target is None:
            continue
        for workload in workloads_for_service(target, workloads):
            routed_workloads.add(workload.name)

    used_slugs: set[str] = set()
    proposals: list[ProposedNamespace] = []
    for members in grouped:
        group = tuple(by_name[name] for name in members)
        role = _workload_role(group, routed_workloads)
        slug = _group_slug(group, role, used_slugs)
        used_slugs.add(slug)
        app_groups = tuple(sorted({_app_key(wl) for wl in group}))
        proposals.append(
            ProposedNamespace(
                suggested_name=_suggested_name(namespace, slug),
                slug=slug,
                role=role,
                workload_names=tuple(wl.name for wl in group),
                rationale=_rationale(group, edges, role),
                app_groups=app_groups,
            )
        )

    name_to_slug = {
        workload_name: proposal.slug
        for proposal in proposals
        for workload_name in proposal.workload_names
    }
    outbound: dict[str, set[str]] = defaultdict(set)
    inbound: dict[str, set[str]] = defaultdict(set)
    residual_by_slug: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        left_slug = name_to_slug.get(edge.left)
        right_slug = name_to_slug.get(edge.right)
        if left_slug is None or right_slug is None or left_slug == right_slug:
            continue
        outbound[left_slug].add(right_slug)
        inbound[right_slug].add(left_slug)
        outbound[right_slug].add(left_slug)
        inbound[left_slug].add(right_slug)
        detail = f"{edge.left} ↔ {edge.right} ({edge.detail})"
        residual_by_slug[left_slug].append(detail)
        residual_by_slug[right_slug].append(detail)

    finalized: list[ProposedNamespace] = []
    for proposal in proposals:
        finalized.append(
            ProposedNamespace(
                suggested_name=proposal.suggested_name,
                slug=proposal.slug,
                role=proposal.role,
                workload_names=proposal.workload_names,
                rationale=proposal.rationale,
                app_groups=proposal.app_groups,
                outbound_to=tuple(sorted(outbound.get(proposal.slug, ()))),
                inbound_from=tuple(sorted(inbound.get(proposal.slug, ()))),
                residual_calls=tuple(sorted(set(residual_by_slug.get(proposal.slug, ())))),
            )
        )

    return NamespacePartition(
        current_namespace=namespace,
        workload_count=workload_count,
        groups=tuple(finalized),
        edges=edges,
        should_split=should_split,
        skip_reason=skip_reason,
    )


def propose_namespace_partition_from_context(
    ctx: AnalysisContext,
) -> NamespacePartition:
    return propose_namespace_partition(
        ctx.namespace,
        ctx.workloads,
        ctx.services,
        ctx.routes,
    )


def analyze_namespace_partition(
    ctx: AnalysisContext,
    builder: FindingBuilder,
) -> None:
    partition = propose_namespace_partition_from_context(ctx)
    if not partition.should_split:
        return

    composition = "; ".join(
        f"`{group.suggested_name}` ({len(group.workload_names)} workloads: "
        + ", ".join(f"`{name}`" for name in group.workload_names[:8])
        + ("…" if len(group.workload_names) > 8 else "")
        + ")"
        for group in partition.groups
    )
    residual_count = sum(len(group.residual_calls) for group in partition.groups) // 2
    builder.add(
        category="ARCH",
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        namespace=ctx.namespace,
        evidence=(
            EvidenceItem(
                description="Workloads no namespace atual",
                value=str(partition.workload_count),
            ),
            EvidenceItem(
                description="Namespaces sugeridos",
                value=str(len(partition.groups)),
            ),
            EvidenceItem(
                description="Composição proposta",
                value=composition,
            ),
            EvidenceItem(
                description="Arestas de comunicação residual entre grupos",
                value=str(residual_count),
            ),
        ),
        analysis=(
            f"O namespace `{ctx.namespace}` concentra {partition.workload_count} "
            "workloads em grupos de aplicação distintos. Sem comunicação "
            "comprovável entre os grupos (Service selector, env, PVC ou "
            "Secret/ConfigMap dedicado), cada grupo é candidato a um namespace "
            f"próprio: {composition}."
        ),
        impact=(
            "Namespaces superpovoados dificultam RBAC, cotas, NetworkPolicy e "
            "o ciclo de vida independente das aplicações."
        ),
        recommendation=(
            "Avaliar a criação dos namespaces da tabela "
            "**Redistribuição sugerida do namespace**, mantendo juntos apenas "
            "workloads que se comunicam ou compartilham dependências dedicadas."
        ),
        limitation=(
            "A proposta usa evidência estática (selector, env, volumes). "
            "Tráfego real, service mesh e NetworkPolicies não estão no dump; "
            "a quebra deve ser validada com o time dono da aplicação."
        ),
    )
