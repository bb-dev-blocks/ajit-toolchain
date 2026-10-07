#!/usr/bin/env bash
# Build + run a set of layers on the C-model, then collect one CSV.
#   ./sweep.sh all|kinds|linearity|<op[:rows]>,... [-j N]
#     all        every representative op (one per config) at ROWS=1
#                → results/<variant>.csv (+ golden_checksums.tsv for reference)
#     kinds      representative ops of every non-conv kind
#     linearity  ops 9 and 46 at ROWS 1, 2, 4
#     list       e.g. 8,46:2  → results/<variant>-<set>.csv
# VARIANT / TFLM_LIB_DIR are passed to build.sh. Each C-model process keeps
# ~3.5 host cores busy, so -j defaults to 4.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
SET="${1:?usage: ./sweep.sh all|kinds|linearity|<op[:rows]>,... [-j N]}"; shift
JOBS=4
[[ "${1:-}" == -j ]] && JOBS="$2"
export VARIANT="${VARIANT:-reference}" TARGET=cmodel

# Representative ops, heaviest single-row work first (shortens the parallel tail).
reps() {
  awk -F'\t' -v k="$1" 'NR>1 && $4==1 && (k=="" || (k=="nonconv" && $2!="CONV_2D")) {
    split($8, s, "x"); print $14 / (length(s) == 4 ? s[2] : 1), $1 }' layers.tsv |
    sort -gr | cut -d' ' -f2
}
case "$SET" in
  all)       ENTRIES="$(reps "")" ;;
  kinds)     ENTRIES="$(reps nonconv)" ;;
  linearity) ENTRIES="9:1 9:2 9:4 46:1 46:2 46:4" ;;
  *)         ENTRIES="$(tr ',' ' ' <<<"$SET")" ;;
esac

one() {
  local L="${1%%:*}" R=1
  [[ "$1" == *:* ]] && R="${1#*:}"
  local W="$HERE/work/$VARIANT/L${L}_R${R}"
  mkdir -p "$W"
  if ! LAYER=$L ROWS=$R ./build.sh > "$W/build.log" 2>&1; then
    echo "sweep: L$L R$R build failed ($W/build.log)"; return 0
  fi
  LAYER=$L ROWS=$R ./run.sh > /dev/null 2>&1 || true
  echo "sweep: L$L R$R done"
}
export -f one
export HERE
tr ' ' '\n' <<<"$ENTRIES" | grep . | xargs -P "$JOBS" -I{} bash -c 'one {}'

OUT="results/$VARIANT.csv"
[[ "$SET" == all ]] || OUT="results/$VARIANT-${SET//[,:]/_}.csv"
GOLDEN=()
[[ "$SET" == all && "$VARIANT" == reference ]] && GOLDEN=(--write-golden)
exec python3 ./collect.py --variant "$VARIANT" --out "$OUT" "${GOLDEN[@]}" $ENTRIES
