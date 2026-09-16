#!/usr/bin/env bash
# Generate TFLM cc arrays (models/wav) under gen/ajit_sparc_default_gcc/genfiles/.
# Caller sets TFLITE_GENERATOR_INPUTS (space-separated paths vs $TFLM).

set -euo pipefail

if [[ -z "${AJIT_HOME:-}" ]]; then
  echo "tflite: set AJIT_HOME (source set_ajit_home)" >&2
  exit 1
fi

if [[ -z "${TFLITE_GENERATOR_INPUTS:-}" ]]; then
  echo "tflite: TFLITE_GENERATOR_INPUTS is empty" >&2
  exit 1
fi

TFLM="${AJIT_HOME}/tflite-micro"
GEN="${TFLM}/gen/ajit_sparc_default_gcc"

echo "tflite: generating cc arrays"
(cd "$TFLM" && python3 tensorflow/lite/micro/tools/generate_cc_arrays.py \
  "${GEN}/genfiles/" $TFLITE_GENERATOR_INPUTS)
