"""Análise de inventário: Routes, ConfigMaps, logs e operadores."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from kubeoptix_core_ai.analysis.context import AnalysisContext
from kubeoptix_core_ai.analysis.findings_builder import FindingBuilder
from kubeoptix_core_ai.analysis.workload_refs import extract_service_calls
from kubeoptix_core_ai.models.finding import Confidence, EvidenceItem, Severity

_DNS_FAILURE_HOST_RE = re.compile(
    r"(?:getaddrinfo\s+ENOTFOUND|ENOTFOUND)\s+([A-Za-z0-9.-]+)|hostname:\s*['\"]?([A-Za-z0-9.-]+)['\"]?",
    re.IGNORECASE,
)


def _all_referenced_configmaps(ctx: AnalysisContext) -> set[str]:
    refs: set[str] = set()
    for workload in ctx.workloads:
        refs.update(workload.referenced_configmaps)
    return refs


def _emit_log_signal_finding(
    builder: FindingBuilder,
    *,
    namespace: str,
    app_group: str,
    signal: str,
    logs: tuple,
    severity: Severity,
    confidence: Confidence,
    analysis: str,
    impact: str,
    recommendation: str,
) -> None:
    pod_names = ", ".join(log.pod_name for log in logs)
    evidence = (
        EvidenceItem(
            description=f"Sinal operacional detectado em logs ({signal})",
            value=f"pods={pod_names}, count={len(logs)}, signal={signal}",
            file_path=logs[0].file_path,
        ),
    )
    builder.add(
        category="LOG",
        severity=severity,
        confidence=confidence,
        namespace=namespace,
        workload=app_group,
        evidence=evidence,
        analysis=analysis,
        impact=impact,
        recommendation=recommendation,
        sources=(),
    )


def _failed_service_hosts_for_log(log) -> tuple[str, ...]:
    try:
        text = Path(log.file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""

    hosts: list[str] = []
    for match in _DNS_FAILURE_HOST_RE.finditer(text):
        host = next((group for group in match.groups() if group), None)
        if host:
            hosts.append(host.split(":", 1)[0])
    return tuple(sorted(set(hosts)))


def _service_match_candidates(hostname: str) -> tuple[str, ...]:
    hostname = hostname.strip().split(":", 1)[0].lower()
    candidates = {hostname}
    if "." in hostname:
        candidates.add(hostname.split(".", 1)[0])
    if hostname.endswith(".svc.cluster.local"):
        candidates.add(hostname.split(".", 1)[0])
    return tuple(sorted(candidates))


def _key_is_service_context(key: str | None) -> bool:
    if key is None:
        return True
    lower_key = key.lower()
    if any(marker in lower_key for marker in ("tz", "timezone", "locale", "lang", "region")):
        return False
    return any(
        marker in lower_key
        for marker in (
            "url",
            "host",
            "endpoint",
            "uri",
            "server",
            "addr",
            "database",
            "db",
            "cache",
            "redis",
            "postgres",
            "mysql",
            "mongo",
            "kafka",
            "rabbit",
            "api",
            "service",
            "gateway",
            "backend",
            "frontend",
            "auth",
            "queue",
            "broker",
        )
    )


def _looks_like_service_instance(host: str, *, key: str | None = None) -> bool:
    original = host.strip().lower().split(":", 1)[0].strip(".")
    host = original
    if not host or host in {"localhost", "127.0.0.1", "0.0.0.0", "example.com", "http", "https"}:
        return False
    if host.endswith(".svc.cluster.local"):
        host = host.split(".", 1)[0]
    elif host.endswith(".svc") or host.endswith(".cluster.local"):
        host = host.split(".", 1)[0]
    elif "." in host:
        # Reject public/external domain-style values that are not in-cluster service names.
        return False
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", host):
        return False
    if any(ch in host for ch in "-.0123456789"):
        return True
    if host in {"api", "db", "web", "ui", "auth", "mq", "svc"}:
        return True
    if key is not None and _key_is_service_context(key):
        return len(host) <= 20 and host not in {"utc", "gmt", "local", "timezone", "america", "sao", "paulo"}
    return False


def _config_value_service_names(value: str, *, key: str | None = None) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()

    if key is not None and not _key_is_service_context(key):
        return ()

    if "/" in text and "://" not in text and ".svc" not in text.lower() and key is not None and not _key_is_service_context(key):
        return ()

    candidates: set[str] = set()
    for host in re.findall(r"(?:https?:\/\/|\/\/)?([A-Za-z0-9][A-Za-z0-9.-]*)(?::\d+)?(?:\/|$)", text):
        host = host.strip().lower().split(":", 1)[0]
        if _looks_like_service_instance(host, key=key):
            candidates.add(host.split(".", 1)[0])

    if not candidates:
        for token in re.findall(r"(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9.-]*)(?::\d+)?", text):
            token = token.strip().lower().split(":", 1)[0]
            if _looks_like_service_instance(token, key=key):
                candidates.add(token.split(".", 1)[0])

    return tuple(sorted(candidates))


def _expected_internal_dependencies_by_app(bundle) -> dict[str, set[str]]:
    by_app: dict[str, set[str]] = defaultdict(set)
    configmap_by_name = {cm.name: cm for cm in bundle.configmaps}
    for workload in bundle.workloads:
        for configmap_name in workload.referenced_configmaps:
            configmap = configmap_by_name.get(configmap_name)
            if configmap is None:
                continue
            for key, value in configmap.data.items():
                by_app[workload.app_group].update(_config_value_service_names(value, key=key))
    return by_app


def build_service_dependency_graph(bundle) -> tuple[tuple[str, str, str], ...]:
    """Retorna arestas workload → serviço, extraídas de env/config e do inventário."""
    edges: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    by_name = {svc.name.lower(): svc.name for svc in bundle.services}
    configmap_by_name = {cm.name: cm for cm in bundle.configmaps}

    for workload in bundle.workloads:
        env_refs = extract_service_calls(workload, {svc.name for svc in bundle.services})
        for service_name, _, env_name in env_refs:
            key = (workload.name, service_name, f"env:{env_name}")
            if key not in seen:
                seen.add(key)
                edges.append(key)

        for configmap_name in workload.referenced_configmaps:
            configmap = configmap_by_name.get(configmap_name)
            if configmap is None:
                continue
            for config_key, value in configmap.data.items():
                for candidate in _config_value_service_names(value, key=config_key):
                    target_name = by_name.get(candidate.lower(), candidate)
                    key = (workload.name, target_name, f"config:{configmap.name}")
                    if key not in seen:
                        seen.add(key)
                        edges.append(key)

    return tuple(sorted(edges, key=lambda item: (item[0], item[1], item[2])))


def _service_dependency_gap_findings(bundle, builder, namespace: str) -> None:
    expected_by_app = _expected_internal_dependencies_by_app(bundle)
    service_names = {svc.name.lower() for svc in bundle.services}
    for workload in bundle.workloads:
        expected = sorted(expected_by_app.get(workload.app_group, set()))
        if not expected:
            continue
        missing = sorted({service for service in expected if service.lower() not in service_names})
        if not missing:
            continue
        builder.add(
            category="CONFIG",
            severity=Severity.MEDIUM,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            workload=workload.app_group,
            evidence=(
                EvidenceItem(
                    description="Dependências internas esperadas mas não presentes no namespace",
                    value=f"expected={', '.join(missing)}, workload={workload.name}",
                    file_path=workload.source.file_path,
                ),
            ),
            analysis=(
                f"O workload `{workload.app_group}` referencia serviços internos `{', '.join(missing)}` "
                "em ConfigMaps/ambientes, mas nenhum `Service` correspondente está disponível no namespace."
            ),
            impact=(
                "A aplicação precisa de dependências que não existem no inventário, elevando risco de "
                "falha de DNS, startup e integridade de serviço."
            ),
            recommendation=(
                "Confirmar a presença do `Service`, `Endpoints` e selectors de destino; ajustar o nome "
                "da dependência ou criar o backend esperado para a aplicação."
            ),
            sources=(workload.source,),
        )

    graph = build_service_dependency_graph(bundle)
    for source, target, reason in graph:
        if source == target:
            continue
        if target.lower() in service_names:
            continue
        source_ref = next((w.source for w in bundle.workloads if w.name == source), None)
        builder.add(
            category="CONFIG",
            severity=Severity.MEDIUM,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            workload=source,
            evidence=(
                EvidenceItem(
                    description="Aresta de dependência de serviço observada",
                    value=f"source={source}, target={target}, reason={reason}",
                    file_path=source_ref.file_path if source_ref else "",
                ),
            ),
            analysis=(
                f"O workload `{source}` referencia o serviço `{target}` em `{reason}`, mas ele não está "
                "presente no namespace e pode gerar falha de resolução/ordem de startup."
            ),
            impact=(
                "A app tentará se conectar a um backend que não está exposto como Service; isso "
                "pode resultar em `ENOTFOUND`, timeouts ou 5xx em runtime."
            ),
            recommendation=(
                "Confirmar se o serviço alvo existe, se o nome está correto e se a dependência foi "
                "declarada com `Service`, `selector` e readiness adequados."
            ),
            sources=((source_ref,) if source_ref is not None else ()),
        )


def _startup_guard_findings(bundle, builder, namespace: str) -> None:
    expected_by_app = _expected_internal_dependencies_by_app(bundle)
    for workload in bundle.workloads:
        expected = expected_by_app.get(workload.app_group, set())
        if not expected:
            continue
        missing_guards = [
            container.name
            for container in workload.containers
            if not (container.readiness_probe or container.startup_probe)
        ]
        if not missing_guards:
            continue
        builder.add(
            category="WORKLOAD",
            severity=Severity.MEDIUM,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            workload=workload.app_group,
            evidence=(
                EvidenceItem(
                    description="Workload com dependência interna e sem readiness/startup guard",
                    value=f"services={', '.join(sorted(expected))}, missing_guards={', '.join(missing_guards)}",
                    file_path=workload.source.file_path,
                ),
            ),
            analysis=(
                f"O workload `{workload.app_group}` depende de serviços internos `{', '.join(sorted(expected))}` "
                "mas alguns containers não possuem `readinessProbe`/`startupProbe`, "
                "o que aumenta risco de ordem de startup e falha de dependência."
            ),
            impact=(
                "A app pode entrar em serviço antes que o backend esteja pronto, resultando em "
                "DNS, timeout ou 5xx em transições de deploy."
            ),
            recommendation=(
                "Adicionar `readinessProbe` e, quando necessário, `startupProbe` para garantir que o "
                "container só receba tráfego após a dependência interna estar pronta."
            ),
            sources=(workload.source,),
        )


def analyze_inventory(ctx: AnalysisContext, builder: FindingBuilder) -> None:
    namespace = ctx.namespace
    bundle = ctx.bundle
    empty_by_app: dict[str, list] = defaultdict(list)
    debug_by_app: dict[str, list] = defaultdict(list)
    signal_hits: dict[str, list] = defaultdict(list)

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

        for signal in log.runtime_signals:
            signal_hits[signal].append(log)

        total_level_lines = sum(log.levels.values())
        if log.line_count > 0 and total_level_lines == log.line_count:
            only_debug = set(log.levels.keys()) <= {"DEBUG", "TRACE"}
            if only_debug and log.levels.get("DEBUG", 0) > 0:
                debug_by_app[log.app_group].append(log)

    _service_dependency_gap_findings(bundle, builder, namespace)
    _startup_guard_findings(bundle, builder, namespace)

    if signal_hits.get("dns_lookup_failure"):
        expected_by_app = _expected_internal_dependencies_by_app(bundle)
        seen_dns: set[tuple[str, str]] = set()
        dns_logs: list = []
        for log in signal_hits["dns_lookup_failure"]:
            key = (log.file_path, log.pod_name)
            if key in seen_dns:
                continue
            seen_dns.add(key)
            dns_logs.append(log)
        dns_logs = tuple(sorted(dns_logs, key=lambda x: x.pod_name))
        dns_by_app: dict[str, list] = defaultdict(list)
        for log in dns_logs:
            dns_by_app[log.app_group].append(log)
        for app_group, logs in dns_by_app.items():
            _emit_log_signal_finding(
                builder,
                namespace=namespace,
                app_group=app_group,
                signal="dns_lookup_failure",
                logs=tuple(logs),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                analysis=(
                    f"Os logs de `{app_group}` mostram falha de resolução de DNS/Service "
                    "interno (`ENOTFOUND`, `fetch failed` ou `getaddrinfo`), sugerindo "
                    "serviço ausente ou ordem de inicialização incorreta."
                ),
                impact=(
                    "Dependências internas deixam de resolver e a aplicação falha ao se "
                    "conectar a serviços do cluster."
                ),
                recommendation=(
                    "Validar `Service`, `Endpoints`, `CoreDNS`, `selector` e ordem de startup; "
                    "conferir se o nome do serviço está correto e se o workload já está pronto."
                ),
            )

            expected_services = sorted(expected_by_app.get(app_group, set()))
            for hostname in _failed_service_hosts_for_log(logs[0]):
                service_matches = [
                    svc.name
                    for svc in bundle.services
                    if any(
                        candidate == svc.name.lower()
                        for candidate in _service_match_candidates(hostname)
                    )
                ]
                expected_matches = [
                    service_name
                    for service_name in expected_services
                    if any(
                        candidate == service_name.lower()
                        for candidate in _service_match_candidates(hostname)
                    )
                ]
                if not service_matches and expected_matches:
                    builder.add(
                        category="CONFIG",
                        severity=Severity.HIGH,
                        confidence=Confidence.HIGH,
                        namespace=namespace,
                        workload=app_group,
                        evidence=(
                            EvidenceItem(
                                description="Dependência interna esperada no ConfigMap/env",
                                value=f"expected={', '.join(sorted(set(expected_matches)))}, host={hostname}, pod={logs[0].pod_name}",
                                file_path=logs[0].file_path,
                            ),
                        ),
                        analysis=(
                            f"O workload `{app_group}` referencia `{', '.join(sorted(set(expected_matches)))}` "
                            "em variáveis de ambiente/ConfigMap, mas o nome não corresponde a um `Service` "
                            "definido no namespace ou sua resolução falha durante startup."
                        ),
                        impact=(
                            "A aplicação depende de um serviço interno que não está disponível ou não "
                            "foi exposto corretamente ao runtime."
                        ),
                        recommendation=(
                            "Verificar o nome do `Service`, confirmar os `endpoints` e garantir que a "
                            "aplicação só acesse dependências após o serviço estar pronto."
                        ),
                        sources=(),
                    )
                    continue
                if not service_matches:
                    continue
                service_names = ", ".join(sorted(set(service_matches)))
                analysis = (
                    f"O workload `{app_group}` falha ao resolver o serviço interno `{service_names}` "
                    "durante a inicialização/execução, o que indica problema de descoberta de DNS "
                    "ou ordem de startup entre dependências do namespace."
                )
                if expected_matches:
                    expected_names = ", ".join(sorted(set(expected_matches)))
                    analysis += (
                        f" A aplicação referencia esse endpoint também em ConfigMap/env (`{expected_names}`), "
                        "confirmando a dependência esperada do namespace."
                    )
                builder.add(
                    category="LOG",
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    namespace=namespace,
                    workload=app_group,
                    evidence=(
                        EvidenceItem(
                            description="Serviço interno não resolvido por DNS",
                            value=f"services={service_names}, host={hostname}, pod={logs[0].pod_name}",
                            file_path=logs[0].file_path,
                        ),
                    ),
                    analysis=analysis,
                    impact=(
                        "A aplicação não consegue alcançar um serviço do mesmo namespace e pode "
                        "ficar em erro durante processamento de requisições."
                    ),
                    recommendation=(
                        "Validar o `Service`, `Endpoints` e readiness do workload alvo; verificar a "
                        "ordem de startup e garantir que o nome do serviço esteja consistente com os "
                        "endpoints e o ConfigMap/env da aplicação."
                    ),
                    sources=(),
                )

    if signal_hits.get("http_5xx"):
        seen_http_5xx: set[tuple[str, str]] = set()
        http_5xx_logs: list = []
        for log in signal_hits["http_5xx"]:
            key = (log.file_path, log.pod_name)
            if key in seen_http_5xx:
                continue
            seen_http_5xx.add(key)
            http_5xx_logs.append(log)
        http_5xx_logs = tuple(sorted(http_5xx_logs, key=lambda x: x.pod_name))
        by_app: dict[str, list] = defaultdict(list)
        for log in http_5xx_logs:
            by_app[log.app_group].append(log)
        for app_group, logs in by_app.items():
            _emit_log_signal_finding(
                builder,
                namespace=namespace,
                app_group=app_group,
                signal="http_5xx",
                logs=tuple(logs),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                analysis=(
                    f"Os logs de `{app_group}` registram respostas HTTP 5xx em endpoints de API "
                    "do namespace, indicando falha de processamento interno ou dependência indisponível."
                ),
                impact=(
                    "Requisições de clientes ou do próprio sistema passam a falhar com erro 500, "
                    "impactando experiência e observabilidade."
                ),
                recommendation=(
                    "Analisar stack trace do endpoint/handler, verificar dependências internas e "
                    "monitorar os códigos de erro 5xx em produção."
                ),
            )

    if signal_hits.get("postgres_trust_auth"):
        seen_pg: set[tuple[str, str]] = set()
        pg_logs: list = []
        for log in signal_hits["postgres_trust_auth"]:
            key = (log.file_path, log.pod_name)
            if key in seen_pg:
                continue
            seen_pg.add(key)
            pg_logs.append(log)
        pg_logs = tuple(sorted(pg_logs, key=lambda x: x.pod_name))
        pg_by_app: dict[str, list] = defaultdict(list)
        for log in pg_logs:
            pg_by_app[log.app_group].append(log)
        for app_group, logs in pg_by_app.items():
            _emit_log_signal_finding(
                builder,
                namespace=namespace,
                app_group=app_group,
                signal="postgres_trust_auth",
                logs=tuple(logs),
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                analysis=(
                    f"O workload `{app_group}` registra autenticação `trust` para conexões locais no PostgreSQL; "
                    "isso reduz a segurança de autenticação do banco em contexto local."
                ),
                impact=(
                    "Conexões locais podem aceitar acessos sem credenciais, ampliando risco de "
                    "autorização indevida em ambientes compartilhados."
                ),
                recommendation=(
                    "Revisar `pg_hba.conf`/ConfigMap de PostgreSQL e remover `trust` para conexões "
                    "locais, preferindo `scram-sha-256` ou autenticação com secret explícito."
                ),
            )

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
    for op in upgrade_ops:
        copied_note = (
            " CSV com reason `Copied` (cópia cluster-wide no namespace)."
            if op.is_cluster_copied
            else ""
        )
        installed = op.version or op.name
        available = op.channel_current_csv or "—"
        builder.add(
            category="OPER",
            severity=Severity.MEDIUM,
            confidence=Confidence.MEDIUM,
            namespace=namespace,
            evidence=(
                EvidenceItem(
                    description="ClusterServiceVersion instalado",
                    value=f"{op.name} (version={installed})",
                    file_path=op.source.file_path,
                ),
                EvidenceItem(
                    description="Canal padrão do catálogo",
                    value=(
                        f"package={op.package_name or '—'}, "
                        f"channel={op.default_channel or '—'}, "
                        f"currentCSV={available}"
                    ),
                ),
            ),
            analysis=(
                f"O operador `{op.display_name or op.name}` não está na versão "
                f"do canal padrão `{op.default_channel or '—'}` "
                f"(instalado `{op.name}`, catálogo `{available}`).{copied_note}"
            ),
            impact=(
                "Versão atrás do canal pode ficar sem correções de segurança "
                "e de compatibilidade com o cluster."
            ),
            recommendation=(
                "Planejar o upgrade no namespace de instalação do operador "
                "(cluster admin), validando o canal e a Subscription — "
                "não há Subscription neste dump."
            ),
            limitation=(
                "Inferência via PackageManifest (currentCSV do canal padrão). "
                "Sem Subscription não é possível afirmar o canal instalado "
                "nem a estratégia de aprovação."
            ),
            sources=(op.source,),
        )
