#!/usr/bin/env bash
# Run a layer built by build.sh (same LAYER / ROWS / VARIANT / TARGET).
# C-model: drops the per-write trace (-w), which only slows the model, and
# writes the full log to logs/<variant>/L<layer>_R<rows>.log, then prints the
# metric table. qemu: cortos2 run with the layer's expected UART lines.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${LAYER:?resnet50_layers: set LAYER=<op index> (see layers.tsv)}"
ROWS="${ROWS:-1}"
VARIANT="${VARIANT:-reference}"
TARGET="${TARGET:-cmodel}"
WORK="${WORK:-$HERE/work/$VARIANT/L${LAYER}_R${ROWS}}"
LOG="${LOG:-$HERE/logs/$VARIANT/L${LAYER}_R${ROWS}.log}"

if [[ "$TARGET" == qemu ]]; then
  cd "$WORK" && exec cortos2 run --target qemu --timeout "${TIMEOUT:-600}"
fi

mkdir -p "$(dirname "$LOG")"
cd "$WORK/cortos_build"
sed -i '/-w ${_MAIN}.wtrace/d' run_cmodel.sh
./run_cmodel.sh > "$LOG" 2>&1
"$HERE/../cmodel_metrics.py" "$LOG" "$WORK/expected_uart.txt"
