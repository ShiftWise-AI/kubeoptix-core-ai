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

if [[ ! -f "${CHART}/Chart.yaml" ]]; then
  echo "Chart Helm não encontrado em ${CHART}" >&2
  exit 1
fi

HELM_ARGS=(upgrade --install "${RELEASE}" "${CHART}" -n "${NAMESPACE}")

for values_file in "${VALUES_FILES[@]}"; do
  if [[ ! -f "${values_file}" ]]; then
    echo "Arquivo de values não encontrado: ${values_file}" >&2
    exit 1
  fi
  HELM_ARGS+=(-f "${values_file}")
done

exec helm "${HELM_ARGS[@]}"
