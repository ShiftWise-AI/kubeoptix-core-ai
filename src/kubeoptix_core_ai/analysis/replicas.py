"""Análise de réplicas."""

from __future__ import annotations

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity


def analyze_replicas(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace

    for workload in ctx.workloads:
        desired = workload.replicas_desired
        ready = workload.replicas_ready

        # CronJob não tem réplicas — verificar schedule
        if workload.kind == "CronJob":
            if not workload.schedule:
                builder.add(
                    category="REPLICA",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="CronJob sem schedule",
                            file_path=workload.source.file_path,
                        ),
                    ),
                    analysis=f"CronJob `{workload.name}` não possui schedule configurado.",
                    sources=(workload.source,),
                )
            continue

        # DaemonSet: uma instância por nó é esperado — não alertar por réplica única
        if workload.kind == "DaemonSet":
            if ready is not None and desired is not None and ready != desired:
                builder.add(
                    category="REPLICA",
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="DaemonSet pods prontos vs desejados",
                            value=f"desired={desired}, ready={ready}",
                            file_path=workload.source.file_path,
                        ),
                    ),
                    analysis=(
                        f"DaemonSet `{workload.name}`: pods prontos ({ready}) "
                        f"diferem dos agendados ({desired})."
                    ),
                    recommendation="Investigar pods não prontos e taints/tolerations.",
                    sources=(workload.source,),
                )
            if workload.pdb is None:
                builder.add(
                    category="REPLICA",
                    severity=Severity.INFO,
                    confidence=Confidence.MEDIUM,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="DaemonSet sem PDB correlacionado",
                            file_path=workload.source.file_path,
                        ),
                    ),
                    analysis=(
                        f"DaemonSet `{workload.name}` não possui PodDisruptionBudget "
                        "correlacionado nos dados coletados."
                    ),
                    recommendation=(
                        "Avaliar PDB para proteger disponibilidade durante manutenção de nós."
                    ),
                    sources=(workload.source,),
                )
            continue

        if desired is None:
            builder.add(
                category="REPLICA",
                severity=Severity.LOW,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="spec.replicas indisponível",
                        file_path=workload.source.file_path,
                    ),
                ),
                analysis=f"Número de réplicas desejadas não disponível para `{workload.name}`.",
                limitation="Informação não disponível nos dados coletados.",
                sources=(workload.source,),
            )
            continue

        if desired == 1:
            builder.add(
                category="REPLICA",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="Réplicas desejadas",
                        value=str(desired),
                        field_path="spec.replicas",
                        file_path=workload.source.file_path,
                    ),
                ),
                analysis=(
                    f"O workload `{workload.name}` ({workload.kind}) opera com uma única "
                    f"réplica (spec.replicas={desired})."
                ),
                impact=(
                    "Risco potencial de indisponibilidade durante rolling updates ou "
                    "falha de nó — não comprovado como indisponibilidade efetiva."
                ),
                recommendation=(
                    "Avaliar aumento de réplicas ou HPA para cargas que exigem HA."
                ),
                sources=(workload.source,),
            )

        if ready is not None and ready != desired:
            builder.add(
                category="REPLICA",
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="Réplicas desejadas vs prontas",
                        value=f"desired={desired}, ready={ready}",
                        field_path="status.readyReplicas",
                        file_path=workload.source.file_path,
                    ),
                ),
                analysis=(
                    f"Réplicas prontas ({ready}) diferem das desejadas ({desired})."
                ),
                impact="Capacidade efetiva do workload pode estar reduzida.",
                recommendation="Investigar status dos pods e eventos do namespace.",
                sources=(workload.source,),
            )

        if workload.hpa and desired is not None:
            if (
                workload.hpa.min_replicas is not None
                and desired < workload.hpa.min_replicas
            ):
                builder.add(
                    category="REPLICA",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="Réplicas abaixo do HPA minReplicas",
                            value=(
                                f"replicas={desired}, "
                                f"minReplicas={workload.hpa.min_replicas}"
                            ),
                            file_path=workload.hpa.source.file_path,
                        ),
                    ),
                    analysis=(
                        "Réplicas atuais estão abaixo do mínimo configurado no HPA."
                    ),
                    recommendation="Verificar status do HPA e condições de scaling.",
                    sources=(workload.hpa.source, workload.source),
                )

        if workload.vpa and workload.vpa.update_mode == "Off":
            builder.add(
                category="REPLICA",
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                evidence=(
                    EvidenceItem(
                        description="VPA em modo Off",
                        value=f"vpa={workload.vpa.name}, mode=Off",
                        file_path=workload.vpa.source.file_path,
                    ),
                ),
                analysis=(
                    f"VPA `{workload.vpa.name}` associado a `{workload.name}` está em "
                    "modo Off — recomendações não são aplicadas automaticamente."
                ),
                recommendation="Revisar recomendações do VPA e ajustar requests manualmente.",
                sources=(workload.vpa.source, workload.source),
            )

        if workload.pdb:
            pdb = workload.pdb
            pdb_desc = []
            if pdb.min_available is not None:
                pdb_desc.append(f"minAvailable={pdb.min_available}")
            if pdb.max_unavailable is not None:
                pdb_desc.append(f"maxUnavailable={pdb.max_unavailable}")
            if desired is not None and desired == 1 and pdb.min_available == 1:
                builder.add(
                    category="REPLICA",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.MEDIUM,
                    namespace=namespace,
                    workload=workload.name,
                    evidence=(
                        EvidenceItem(
                            description="PDB com réplica única",
                            value=", ".join(pdb_desc) or pdb.name,
                            file_path=pdb.source.file_path,
                        ),
                    ),
                    analysis=(
                        f"PDB `{pdb.name}` com minAvailable=1 e workload com réplica única "
                        "impede evictions voluntárias durante manutenção."
                    ),
                    recommendation=(
                        "Aumentar réplicas ou ajustar PDB para permitir manutenção de nós."
                    ),
                    sources=(pdb.source, workload.source),
                )

    # Concentração cross-workload entre workloads com nodeSelector (pool app)
    constrained = [
        w
        for w in ctx.workloads
        if w.node_selector and (w.replicas_desired or 0) >= 2 and len(w.placements) >= 2
    ]
    if len(constrained) >= 2:
        shared_nodes: set[str] = set()
        for w in constrained:
            for p in w.placements:
                if p.node_name:
                    shared_nodes.add(p.node_name)
        total_pods = sum(len(w.placements) for w in constrained)
        if len(shared_nodes) <= 2 and total_pods >= 4:
            wl_names = sorted(w.name for w in constrained)
            builder.add(
                category="REPLICA",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                namespace=namespace,
                evidence=(
                    EvidenceItem(
                        description="Workloads com nodeSelector concentrados em poucos nós",
                        value=(
                            f"workloads={wl_names}, nós={sorted(shared_nodes)}, "
                            f"pods={total_pods}"
                        ),
                    ),
                ),
                analysis=(
                    f"{len(wl_names)} workload(s) com nodeSelector e ≥2 réplicas compartilham "
                    f"apenas {len(shared_nodes)} nó(s): {', '.join(sorted(shared_nodes))}."
                ),
                impact=(
                    "Falha de um único nó pode afetar réplicas de múltiplas aplicações "
                    "simultaneamente, reduzindo resiliência do namespace."
                ),
                recommendation=(
                    "Configurar podAntiAffinity ou topologySpreadConstraints para "
                    "distribuir réplicas entre nós distintos."
                ),
                sources=tuple(w.source for w in constrained),
            )
