#!/usr/bin/env bash
# Build one ResNet-50 op as a cortos2 program.
#   LAYER=<op index from layers.tsv>  (required)
#   ROWS=<output rows>                (default 1)
#   VARIANT=<name>                    (default reference; names the work/log dirs)
#   TFLM_LIB_DIR=<dir>                (default tflite-micro/gen/ajit_sparc_default_gcc/lib,
#                                      relative to $AJIT_HOME or absolute)
#   TARGET=cmodel|qemu                (default cmodel)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${AJIT_HOME:?resnet50_layers: source set_ajit_home}"
: "${LAYER:?resnet50_layers: set LAYER=<op index> (see layers.tsv)}"
ROWS="${ROWS:-1}"
VARIANT="${VARIANT:-reference}"
TARGET="${TARGET:-cmodel}"
TFLM_LIB_DIR="${TFLM_LIB_DIR:-tflite-micro/gen/ajit_sparc_default_gcc/lib}"
[[ "$TFLM_LIB_DIR" = /* ]] || TFLM_LIB_DIR="$AJIT_HOME/$TFLM_LIB_DIR"
WORK="${WORK:-$HERE/work/$VARIANT/L${LAYER}_R${ROWS}}"

mkdir -p "$WORK"
python3 "$HERE/generate_layer.py" --layer "$LAYER" --rows "$ROWS" --gen "$WORK/gen"
sed -e "s|@HERE@|$HERE|g" -e "s|@GEN@|$WORK/gen|g" \
    -e "s|@TFLM_LIB_DIR@|$TFLM_LIB_DIR|g" \
    "$HERE/config.yaml.tpl" > "$WORK/config.yaml"
cp "$HERE/placeholder.c" "$WORK/"
printf 'invoke: ok\nlayer_done\n' > "$WORK/expected_uart.txt"
git -C "$TFLM_LIB_DIR" rev-parse --short HEAD > "$WORK/tflm_rev" 2>/dev/null \
  || echo unknown > "$WORK/tflm_rev"
cd "$WORK"
cortos2 build --target "$TARGET" "$@"
