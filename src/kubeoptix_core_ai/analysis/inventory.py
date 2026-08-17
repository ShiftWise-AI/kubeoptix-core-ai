"""Análise de inventário: Routes, ConfigMaps, logs e operadores."""

from __future__ import annotations

from collections import defaultdict

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity


def _all_referenced_configmaps(ctx: AnalysisContext) -> set[str]:
    refs: set[str] = set()
    for workload in ctx.workloads:
        refs.update(workload.referenced_configmaps)
    return refs


def analyze_inventory(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace
    bundle = ctx.bundle
    empty_by_app: dict[str, list] = defaultdict(list)
    debug_by_app: dict[str, list] = defaultdict(list)

    for route in bundle.routes:
        if route.tls_insecure_policy and route.tls_insecure_policy.lower() == "allow":
            builder.add(
                category="ROUTE",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=route.target_service,
                evidence=(
                    EvidenceItem(
                        description="Route TLS insecureEdgeTerminationPolicy",
                        value=f"host={route.host}, policy={route.tls_insecure_policy}",
                        file_path=route.source.file_path,
                    ),
                ),
                analysis=(
                    f"A Route `{route.name}` aceita tráfego HTTP inseguro "
                    f"(`insecureEdgeTerminationPolicy: Allow`) para `{route.host}`."
                ),
                impact="Dados em trânsito podem ser expostos se clientes usam HTTP.",
                recommendation=(
                    "Alterar `insecureEdgeTerminationPolicy` para `Redirect` ou "
                    "`None` conforme política de segurança."
                ),
                sources=(route.source,),
            )

    referenced_cm = _all_referenced_configmaps(ctx)
    for cm in bundle.configmaps:
        if cm.name in referenced_cm:
            continue
        # ConfigMaps de plataforma injetados automaticamente
        if cm.name in ("kube-root-ca.crt", "openshift-service-ca.crt"):
            continue
        builder.add(
            category="CONFIG",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="ConfigMap sem referência em workloads",
                    value=f"keys={list(cm.keys)}",
                    file_path=cm.source.file_path,
                ),
            ),
            analysis=(
                f"ConfigMap `{cm.name}` não é referenciado por envFrom, volume ou "
                "env valueFrom nos workloads analisados."
            ),
            recommendation=(
                "Remover se órfão ou referenciar explicitamente em envFrom/volumeMounts."
            ),
            sources=(cm.source,),
        )

    for log in bundle.pod_logs:
        if log.empty:
            empty_by_app.setdefault(log.app_group, []).append(log)
            continue

        total_level_lines = sum(log.levels.values())
        if log.line_count > 0 and total_level_lines == log.line_count:
            only_debug = set(log.levels.keys()) <= {"DEBUG", "TRACE"}
            if only_debug and log.levels.get("DEBUG", 0) > 0:
                debug_by_app[log.app_group].append(log)

    for app_group, logs in empty_by_app.items():
        pod_names = ", ".join(l.pod_name for l in logs)
        builder.add(
            category="LOG",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            namespace=namespace,
            workload=app_group,
            evidence=(
                EvidenceItem(
                    description="Logs de pod vazios na amostra",
                    value=f"pods={pod_names}, count={len(logs)}",
                ),
            ),
            analysis=(
                f"{len(logs)} arquivo(s) de log de `{app_group}` não contêm linhas "
                "na amostra coletada."
            ),
            impact="Troubleshooting via `oc logs` pode ser impossível.",
            recommendation=(
                "Verificar se a aplicação escreve em stdout/stderr ou apenas em arquivo."
            ),
            sources=(),
        )

    for app_group, logs in debug_by_app.items():
        total_lines = sum(l.line_count for l in logs)
        levels_merged: dict[str, int] = {}
        for log in logs:
            for level, count in log.levels.items():
                levels_merged[level] = levels_merged.get(level, 0) + count
        builder.add(
            category="LOG",
            severity=Severity.MEDIUM,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            workload=app_group,
            evidence=(
                EvidenceItem(
                    description="Distribuição agregada de níveis de log",
                    value=f"pods={len(logs)}, lines={total_lines}, levels={levels_merged}",
                    file_path=logs[0].file_path,
                ),
            ),
            analysis=(
                f"100% das {total_lines} linhas amostradas de {len(logs)} pod(s) de "
                f"`{app_group}` são nível DEBUG/TRACE."
            ),
            impact=(
                "Volume de log elevado em produção; possível ausência de eventos "
                "INFO/WARN/ERROR de negócio na amostra."
            ),
            recommendation=(
                "Elevar nível padrão para INFO em produção; reservar DEBUG para "
                "troubleshooting pontual."
            ),
            sources=(),
        )

    upgrade_ops = [
        op for op in bundle.operators if op.upgrade_status == "UpgradeAvailable"
    ]
    if upgrade_ops:
        names = ", ".join(op.name for op in upgrade_ops[:5])
        builder.add(
            category="OPER",
            severity=Severity.INFO,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="Operadores com upgrade no canal padrão",
                    value=names,
                ),
            ),
            analysis=(
                f"{len(upgrade_ops)} ClusterServiceVersion(s) com versão mais recente "
                "disponível no canal padrão do catálogo (phase Copied — cluster-wide)."
            ),
            recommendation=(
                "Avaliar upgrade dos operadores listados em ambiente não produtivo."
            ),
            limitation=(
                "Inferência via PackageManifest; não há Subscription neste dump."
            ),
        )
