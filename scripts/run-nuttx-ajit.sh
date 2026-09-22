#!/usr/bin/env bash
# Foreground qemu-ajit with the terminal on nsh>. Quit: Ctrl-A then X.
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v qemu-system-sparc >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  source ./set_ajit_home
  # shellcheck disable=SC1091
  source docker/ajit_build/ajit_env
fi

mode="${1:-}"
case "$mode" in
  nsh) smp=1 ;;
  smp) smp=2 ;;
  *)
    echo "usage: $0 nsh|smp" >&2
    exit 2
    ;;
esac

test -f "$ROOT/nuttx/nuttx"
if [ "$mode" = smp ] && ! grep -q '^CONFIG_SMP=y' "$ROOT/nuttx/.config" 2>/dev/null; then
  echo "nuttx is not built as ajit1-qemu:smp" >&2
  exit 1
fi
exec qemu-system-sparc \
  -M ajit1_generic -cpu AJIT1 -smp "$smp" -m 128M \
  -nographic -kernel "$ROOT/nuttx/nuttx"
