#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Uso: $0 <diretório-metadados> <diretório-saída>" >&2
  echo "" >&2
  echo "  diretório-metadados  Pasta com namespaces e worknodes (subdir worknodes/ ou ../worknodes/)" >&2
  echo "  diretório-saída      Pasta onde os relatórios .md serão gravados" >&2
  exit 1
}

[[ $# -eq 2 ]] || usage

METADATA_DIR="$(cd "$1" && pwd)"
OUTPUT_DIR="$2"
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec kubeoptix-core-ai run --metadata-dir "$METADATA_DIR" --output "$OUTPUT_DIR"
