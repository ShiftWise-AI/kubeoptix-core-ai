#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART="${ROOT}/helm/kubeoptix-core-ai"
RELEASE="kubeoptix-core-ai"
NAMESPACE="shiftwise-ai"
VALUES_FILES=()

usage() {
  cat <<'EOF'
Uso:
  install.sh -f <values.example.yaml> [-r <release>]

Options:
  -f  Arquivo de values do Helm (obrigatório; pode ser repetido)
  -r  Nome do release Helm (padrão: kubeoptix-core-ai)
  -h  Ajuda

Namespace de instalação: shiftwise-ai (fixo)

Exemplo:
  ./install.sh -f ./helm/kubeoptix-core-ai/values.example.yaml
EOF
}

while getopts ":f:r:h" opt; do
  case "${opt}" in
    f) VALUES_FILES+=("${OPTARG}") ;;
    r) RELEASE="${OPTARG}" ;;
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

echo "Instalação concluída com sucesso."
