#!/usr/bin/env bash
set -euo pipefail
export TFLITE_QEMU_TIMEOUT="${TFLITE_QEMU_TIMEOUT:-300}"
exec python3 "$(cd "$(dirname "$0")/.." && pwd)/run_qemu_elf.py" "$@"
