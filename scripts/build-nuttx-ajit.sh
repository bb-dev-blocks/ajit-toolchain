#!/usr/bin/env bash
# Build ajit1-qemu:nsh, ajit1-qemu:smp, and ajit1-qemu:tflite.
# Each ELF is copied to build/ before the next configure wipes nuttx/nuttx.
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v sparc-linux-gcc >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  source ./set_ajit_home
  # shellcheck disable=SC1091
  source docker/ajit_build/ajit_env
fi

export CROSSDEV=sparc-linux-
mkdir -p "$ROOT/build"

build_one() {
  local name="$1"
  echo "===== ajit1-qemu:${name} ====="
  cd "$ROOT/nuttx"
  make distclean >/dev/null 2>&1 || true
  rm -f Make.defs .config .version
  ./tools/configure.sh -E -l -a ../apps "ajit1-qemu:${name}"
  make -j"$(nproc)"
  cp -f nuttx "$ROOT/build/nuttx-${name}"
  echo "OK build/nuttx-${name}"
}

build_one nsh
build_one smp
build_one tflite
