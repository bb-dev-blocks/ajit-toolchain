#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [[ -z "${AJIT_HOME:-}" ]]; then
  echo "resnet50: source set_ajit_home" >&2
  exit 1
fi
if [[ $# -ge 1 && "$1" != -* ]]; then
  export INPUT="$1"
  shift
fi
python3 "$HERE/generate_runtime.py"
cortos build --target qemu "$@"
