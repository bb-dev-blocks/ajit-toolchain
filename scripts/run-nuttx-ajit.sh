#!/usr/bin/env bash
# Foreground qemu-ajit with the terminal on nsh>. Quit: Ctrl-A then X.
# Builds ajit1-qemu:<mode> first when nuttx/nuttx is missing or is another config.
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v qemu-system-sparc >/dev/null 2>&1 \
  || ! command -v sparc-linux-gcc >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  source ./set_ajit_home
  # shellcheck disable=SC1091
  source docker/ajit_build/ajit_env
fi
export CROSSDEV=sparc-linux-

mode="${1:-}"
case "$mode" in
  nsh) smp=1 ;;
  smp) smp=2 ;;
  tflite) smp=1 ;;
  *)
    echo "usage: $0 nsh|smp|tflite" >&2
    exit 2
    ;;
esac

config_ok() {
  case "$mode" in
    nsh)
      grep -q '^CONFIG_ARCH_BOARD_AJIT1_QEMU=y' "$ROOT/nuttx/.config" 2>/dev/null \
        && ! grep -q '^CONFIG_SMP=y' "$ROOT/nuttx/.config" \
        && ! grep -q '^CONFIG_AJIT1_QEMU_TFLITE=y' "$ROOT/nuttx/.config"
      ;;
    smp)
      grep -q '^CONFIG_SMP=y' "$ROOT/nuttx/.config" 2>/dev/null
      ;;
    tflite)
      grep -q '^CONFIG_AJIT1_QEMU_TFLITE=y' "$ROOT/nuttx/.config" 2>/dev/null
      ;;
  esac
}

tflite_inputs_newer() {
  [ "$mode" = tflite ] || return 1
  [ -d "$ROOT/tflite-inputs" ] || return 1
  [ -f "$ROOT/nuttx/nuttx" ] || return 1
  find "$ROOT/tflite-inputs" -newer "$ROOT/nuttx/nuttx" -print -quit | grep -q .
}

if [ ! -f "$ROOT/nuttx/nuttx" ] || ! config_ok; then
  echo "building ajit1-qemu:${mode}"
  cd "$ROOT/nuttx"
  make distclean >/dev/null 2>&1 || true
  rm -f Make.defs .config .version
  ./tools/configure.sh -E -l -a ../apps "ajit1-qemu:${mode}"
  make -j"$(nproc)"
  cd "$ROOT"
elif tflite_inputs_newer; then
  echo "rebuilding ajit1-qemu:tflite for tflite-inputs"
  cd "$ROOT/nuttx"
  make -j"$(nproc)"
  cd "$ROOT"
fi

exec qemu-system-sparc \
  -M ajit1_generic -cpu AJIT1 -smp "$smp" -m 128M \
  -nographic -kernel "$ROOT/nuttx/nuttx"
