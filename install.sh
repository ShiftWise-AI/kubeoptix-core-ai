#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART="${ROOT}/helm/kubeoptix-core-ai"
RELEASE="kubeoptix-core-ai"
NAMESPACE="shiftwise-ai"
VALUES_FILES=()
ENABLE_ORPHAN_CLEANUP="true"

wait_for_imagestream_tag() {
  local namespace="$1"
  local bc_name="$2"
  local timeout_seconds="${3:-300}"

  local output_to
  output_to="$(oc get buildconfig "${bc_name}" -n "${namespace}" -o jsonpath='{.spec.output.to.name}' 2>/dev/null || true)"

  if [[ -z "${output_to}" ]]; then
    echo "Aviso: BuildConfig ${bc_name} sem spec.output.to.name; pulando espera de ImageStreamTag." >&2
    return 0
  fi

  echo "Aguardando publicação de ImageStreamTag ${output_to} (até ${timeout_seconds}s)..."

  local elapsed=0
  while [[ ${elapsed} -lt ${timeout_seconds} ]]; do
    if oc get istag "${output_to}" -n "${namespace}" >/dev/null 2>&1; then
      echo "ImageStreamTag disponível: ${output_to}"
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done

  echo "Tempo esgotado aguardando ImageStreamTag ${output_to}." >&2
  echo "Diagnóstico rápido:" >&2
  oc get buildconfig "${bc_name}" -n "${namespace}" -o yaml | tail -30 >&2 || true
  oc get is,istag -n "${namespace}" | grep -E "${bc_name}|${output_to%%:*}|NAME" >&2 || true
  return 1
}

kind_alias() {
  local kind="$1"
  case "${kind}" in
    BuildConfig) echo "buildconfig" ;;
    ImageStream) echo "imagestream" ;;
    StatefulSet) echo "statefulset" ;;
    Service) echo "service" ;;
    ConfigMap) echo "configmap" ;;
    Secret) echo "secret" ;;
    Route) echo "route.route.openshift.io" ;;
    Certificate) echo "certificate.cert-manager.io" ;;
    Issuer) echo "issuer.cert-manager.io" ;;
    *)
      # Helm manifest kinds are CamelCase; convert to lowercase for oc resource output.
      echo "${kind}" | tr '[:upper:]' '[:lower:]'
      ;;
  esac
}

normalize_resource_ref() {
  local resource_ref="$1"
  local kind_part="${resource_ref%/*}"
  local name_part="${resource_ref##*/}"
  kind_part="${kind_part%%.*}"
  echo "${kind_part}/${name_part}"
}

cleanup_orphan_resources() {
  local release="$1"
  local namespace="$2"

  local expected_file
  local managed_file
  expected_file="$(mktemp)"
  managed_file="$(mktemp)"

  trap 'rm -f "${expected_file}" "${managed_file}"' RETURN

  if ! helm get manifest "${release}" -n "${namespace}" >/dev/null 2>&1; then
    echo "Aviso: não foi possível obter o manifest do release para cleanup de órfãos." >&2
    return 0
  fi

  helm get manifest "${release}" -n "${namespace}" \
    | awk '
      /^kind:[[:space:]]+/ { kind=$2 }
      /^metadata:[[:space:]]*$/ { inmeta=1; next }
      inmeta && /^[[:space:]]+name:[[:space:]]+/ {
        name=$2
        gsub(/"/, "", name)
        print kind "/" name
        inmeta=0
      }
      /^---[[:space:]]*$/ { inmeta=0; kind="" }
    ' \
    | while IFS='/' read -r raw_kind raw_name; do
        [[ -z "${raw_kind}" || -z "${raw_name}" ]] && continue
        printf '%s/%s\n' "$(kind_alias "${raw_kind}")" "${raw_name}"
      done \
    | while IFS= read -r expected_resource; do
        normalize_resource_ref "${expected_resource}"
      done \
    | sort -u >"${expected_file}"

  local cleanup_kinds=(
    "configmap"
    "secret"
    "service"
    "route.route.openshift.io"
    "certificate.cert-manager.io"
    "issuer.cert-manager.io"
    "buildconfig"
    "imagestream"
  )

  : >"${managed_file}"
  for kind in "${cleanup_kinds[@]}"; do
    oc get "${kind}" -n "${namespace}" \
      -l "app.kubernetes.io/instance=${release}" \
      -o name --ignore-not-found 2>/dev/null >>"${managed_file}" || true
  done

  if [[ ! -s "${managed_file}" ]]; then
    echo "Cleanup pós-instalação: nenhum recurso gerenciado encontrado para avaliar órfãos."
    return 0
  fi

  sort -u -o "${managed_file}" "${managed_file}"

  local deleted_any="false"
  while IFS= read -r resource; do
    [[ -z "${resource}" ]] && continue
    if ! grep -Fxq "$(normalize_resource_ref "${resource}")" "${expected_file}"; then
      echo "Removendo órfão: ${resource}"
      oc delete -n "${namespace}" "${resource}" --ignore-not-found=true >/dev/null 2>&1 || true
      deleted_any="true"
    fi
  done <"${managed_file}"

  if [[ "${deleted_any}" == "false" ]]; then
    echo "Cleanup pós-instalação: nenhum órfão encontrado."
  fi
}

usage() {
  cat <<'EOF'
Uso:
  install.sh -f <values.example.yaml> [-r <release>] [-x]

Options:
  -f  Arquivo de values do Helm (obrigatório; pode ser repetido)
  -r  Nome do release Helm (padrão: kubeoptix-core-ai)
  -x  Pular cleanup pós-instalação de recursos órfãos
  -h  Ajuda

Namespace de instalação: shiftwise-ai (fixo)

Exemplo:
  ./install.sh -f ./helm/kubeoptix-core-ai/values.example.yaml
EOF
}

while getopts ":f:r:xh" opt; do
  case "${opt}" in
    f) VALUES_FILES+=("${OPTARG}") ;;
    r) RELEASE="${OPTARG}" ;;
    x) ENABLE_ORPHAN_CLEANUP="false" ;;
    h)
      usage
      exit 0
      ;;
    :)
      echo "Opção -${OPTARG} requer um argumento." >&2
      usage
      exit 1
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

shift $((OPTIND - 1))

if [[ $# -gt 0 ]]; then
  echo "Argumentos inesperados: $*" >&2
  usage
  exit 1
fi

if [[ ${#VALUES_FILES[@]} -eq 0 ]]; then
  echo "Informe o arquivo de values com -f." >&2
  usage
  exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "helm não encontrado no PATH." >&2
  exit 1
fi

if ! command -v oc >/dev/null 2>&1; then
  echo "oc não encontrado no PATH." >&2
  exit 1
fi

if ! oc whoami >/dev/null 2>&1; then
  echo "Sem acesso ao cluster OpenShift (oc whoami falhou)." >&2
  exit 1
fi

if [[ ! -f "${CHART}/Chart.yaml" ]]; then
  echo "Chart Helm não encontrado em ${CHART}" >&2
  exit 1
fi

for values_file in "${VALUES_FILES[@]}"; do
  if [[ ! -f "${values_file}" ]]; then
    echo "Arquivo de values não encontrado: ${values_file}" >&2
    exit 1
  fi
done

if ! oc get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "Criando namespace ${NAMESPACE}..."
  oc create namespace "${NAMESPACE}"
fi

HELM_ARGS=(
  upgrade --install "${RELEASE}" "${CHART}"
  -n "${NAMESPACE}"
  --create-namespace
)

for values_file in "${VALUES_FILES[@]}"; do
  HELM_ARGS+=(-f "${values_file}")
done

echo "Instalando release ${RELEASE} no namespace ${NAMESPACE}..."
helm "${HELM_ARGS[@]}"

SA_NAME="$(oc get statefulset "${RELEASE}" -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.serviceAccountName}' 2>/dev/null || true)"
if [[ -n "${SA_NAME}" ]] && ! oc get serviceaccount "${SA_NAME}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo "StatefulSet referencia ServiceAccount inexistente (${SA_NAME}); recriando workload..."
  oc delete statefulset "${RELEASE}" -n "${NAMESPACE}" --wait=true
  helm "${HELM_ARGS[@]}"
fi

BC_NAME="${RELEASE}"
if oc get buildconfig "${BC_NAME}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo
  echo "Iniciando build OpenShift (${BC_NAME})..."
  if ! oc start-build "${BC_NAME}" --wait -n "${NAMESPACE}"; then
    BUILD_NUM="$(oc get buildconfig "${BC_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.lastVersion}')"
    echo "Build falhou (build/${BC_NAME}-${BUILD_NUM}). Últimos logs:" >&2
    oc logs -n "${NAMESPACE}" "build/${BC_NAME}-${BUILD_NUM}" --tail=50 2>/dev/null || true
    exit 1
  fi
  echo "Build concluído."

  if ! wait_for_imagestream_tag "${NAMESPACE}" "${BC_NAME}" 300; then
    exit 1
  fi

  if oc get statefulset "${RELEASE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
    echo "Reiniciando StatefulSet para carregar a nova imagem..."
    oc rollout restart "statefulset/${RELEASE}" -n "${NAMESPACE}"
    oc rollout status "statefulset/${RELEASE}" -n "${NAMESPACE}" --timeout=180s
  fi
fi

echo
echo "Artefatos criados:"
oc get statefulset,svc,bc,is -n "${NAMESPACE}" -l "app.kubernetes.io/instance=${RELEASE}" 2>/dev/null \
  || oc get statefulset,svc,bc,is -n "${NAMESPACE}" | grep -E "${RELEASE}|core-ai|NAME" || true

echo
POD_NAME="$(oc get pods -n "${NAMESPACE}" -l "app.kubernetes.io/instance=${RELEASE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "${POD_NAME}" ]]; then
  echo "AVISO: nenhum pod encontrado para ${RELEASE}." >&2
  echo "Verifique eventos do StatefulSet (comum: SCC rejeitando runAsUser fixo):" >&2
  oc describe statefulset "${RELEASE}" -n "${NAMESPACE}" 2>/dev/null | tail -20 || true
  exit 1
fi

echo "Pod: ${POD_NAME}"
oc get pod "${POD_NAME}" -n "${NAMESPACE}"
echo
echo "Aguardando pod ficar Ready (até 3 min)..."
if ! oc wait --for=condition=Ready "pod/${POD_NAME}" -n "${NAMESPACE}" --timeout=180s; then
  echo "Pod ainda não está Ready. Eventos recentes:" >&2
  oc describe pod "${POD_NAME}" -n "${NAMESPACE}" | tail -30
  exit 1
fi

echo
if [[ "${ENABLE_ORPHAN_CLEANUP}" == "true" ]]; then
  echo "Executando cleanup pós-instalação de recursos órfãos do release..."
  cleanup_orphan_resources "${RELEASE}" "${NAMESPACE}"
else
  echo "Cleanup pós-instalação desabilitado por parâmetro (-x)."
fi

echo "Instalação concluída com sucesso."
