#!/usr/bin/env bash
set -euo pipefail
cd cortos_build
log="$(mktemp)"
./run_cmodel.sh | tee "$log"
while IFS= read -r line; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  grep -F -q -- "$line" "$log" || { echo "tflite: C-model missing UART: $line" >&2; exit 1; }
done < ../expected_uart.txt
rm -f "$log"
