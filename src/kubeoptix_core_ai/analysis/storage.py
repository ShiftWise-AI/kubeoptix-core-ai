"""Análise de storage."""

from __future__ import annotations

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity


def analyze_storage(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace
    pvc_names = {pvc.name for pvc in ctx.pvcs}

    any_storage = False

    for workload in ctx.workloads:
        if not workload.volumes and not workload.volume_mounts:
            continue

        any_storage = True
        for volume in workload.volumes:
            if volume.volume_type == "persistentVolumeClaim" and volume.claim_name:
                if volume.claim_name not in pvc_names:
                    builder.add(
                        category="STORAGE",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.MEDIUM,
                        namespace=namespace,
                        workload=workload.name,
                        evidence=(
                            EvidenceItem(
                                description="PVC referenciado não encontrado na coleta",
                                value=volume.claim_name,
                                field_path=volume.source.field_path,
                                file_path=volume.source.file_path,
                            ),
                        ),
                        analysis=(
                            f"O volume `{volume.name}` referencia PVC "
                            f"`{volume.claim_name}`, ausente em "
                            "`resources/persistentvolumeclaims/`."
                        ),
                        impact=(
                            "PVC pode existir no cluster mas não ter sido coletado, "
                            "ou a referência pode estar incorreta."
                        ),
                        limitation=(
                            "Informação de PVC não disponível nos dados coletados "
                            "para este namespace."
                        ),
                        sources=(workload.source,),
                    )

        for mount in workload.volume_mounts:
            any_storage = True
            builder.add(
                category="STORAGE",
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                namespace=namespace,
                workload=workload.name,
                container=mount.container_name,
                evidence=(
                    EvidenceItem(
                        description="volumeMount configurado",
                        value=f"{mount.name} → {mount.mount_path}",
                        field_path=mount.source.field_path,
                        file_path=mount.source.file_path,
                        container=mount.container_name,
                    ),
                ),
                analysis=(
                    f"Container `{mount.container_name}` monta volume `{mount.name}` "
                    f"em `{mount.mount_path}`."
                ),
                sources=(workload.source,),
            )

    for pvc in ctx.pvcs:
        any_storage = True
        size = pvc.storage_request.raw if pvc.storage_request else "indisponível"
        builder.add(
            category="STORAGE",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="PVC no namespace",
                    value=f"{pvc.name} ({size})",
                    file_path=pvc.source.file_path,
                ),
            ),
            analysis=(
                f"PVC `{pvc.name}` encontrado com request de storage `{size}`."
            ),
            sources=(pvc.source,),
        )

    if not any_storage and not ctx.pvcs:
        builder.add(
            category="STORAGE",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            namespace=namespace,
            analysis=(
                "Nenhum volume persistente, volumeMount ou PVC encontrado nos dados "
                "coletados para este namespace."
            ),
        )
