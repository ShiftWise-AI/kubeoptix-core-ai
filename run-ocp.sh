#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  run-ocp.sh

Description:
  Gera relatórios Markdown para todos os namespaces em KUBEOPTIX_METADATA_DIR
  e grava em KUBEOPTIX_OUTPUT_DIR (compatível com OpenShift SCC Restricted).

Environment:
  KUBEOPTIX_METADATA_DIR  Diretório raiz dos metadados (padrão: /app/data/assessment)
  KUBEOPTIX_OUTPUT_DIR    Diretório de saída dos relatórios (padrão: /app/data/reports)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 0 ]]; then
  echo "Uso: run-ocp.sh (sem argumentos; configure via variáveis de ambiente)" >&2
  exit 1
fi

METADATA_DIR="${KUBEOPTIX_METADATA_DIR:-/app/data/assessment}"
OUTPUT_DIR="${KUBEOPTIX_OUTPUT_DIR:-/app/data/reports}"

mkdir -p "$OUTPUT_DIR"

exec kubeoptix-core-ai run --metadata-dir "$METADATA_DIR" --output "$OUTPUT_DIR"
