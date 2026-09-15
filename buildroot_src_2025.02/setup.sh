#!/usr/bin/env bash
# Build SPARC32 uClibc-ng toolchain from vendored Buildroot 2025.02.18.
# Source tree stays in git; make O= lives under $AJIT_HOME/build (Darwin volume).
# Does not open buildroot-2025.02.18.tar.gz.

set -euo pipefail

if [[ -z "${AJIT_HOME:-}" ]]; then
  echo "Need AJIT_HOME"
  exit 1
fi

export SRC="$AJIT_HOME/buildroot_src_2025.02"
export BR_SRC="$SRC/buildroot-2025.02.18"
export BUILD_DIR="$AJIT_HOME/build"
export BUILDROOT_DIR_NAME="buildroot-2025.02.18"
export O="$BUILD_DIR/$BUILDROOT_DIR_NAME"
export BR2_DL_DIR="$BUILD_DIR/br-dl"
export BUILD_OUTFILE="$BUILD_DIR/output-2025.02.log"
export DEFCONFIG="$SRC/ajit_sparc32_uclibc_defconfig"

mkdir -p "$BUILD_DIR" "$BR2_DL_DIR" "$O"
exec > >(tee -a "$BUILD_OUTFILE") 2>&1

if [[ ! -d "$BR_SRC" ]]; then
  echo "ERROR: $BR_SRC missing. Extract buildroot-2025.02.18.tar.gz once into that path."
  exit 1
fi
if [[ ! -f "$DEFCONFIG" ]]; then
  echo "ERROR: $DEFCONFIG missing"
  exit 1
fi

# Host bin: Buildroot 2025 uses $O/host/bin (not output/host/usr/bin).
_find_gcc() {
  local p
  for p in "$O/host/bin" "$O/host/usr/bin"; do
    if [[ -x "$p/sparc-buildroot-linux-uclibc-gcc" ]]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

ABS_BIN_DIR_PATH="$(_find_gcc || true)"
if [[ -n "${ABS_BIN_DIR_PATH:-}" ]]; then
  echo "Toolchain already at $ABS_BIN_DIR_PATH"
  export ABS_BIN_DIR_PATH
  # shellcheck source=/dev/null
  source "$SRC/pathsetup.sh"
  exit 0
fi

echo "Configuring $BR_SRC O=$O"
make -C "$BR_SRC" O="$O" BR2_DEFCONFIG="$DEFCONFIG" defconfig
echo "Building toolchain (make toolchain)"
make -C "$BR_SRC" O="$O" toolchain

ABS_BIN_DIR_PATH="$(_find_gcc)"
export ABS_BIN_DIR_PATH

_uclibc_lib=$(echo "$O"/build/uclibc-ng-*/lib)
_sysroot_lib="$O/host/sparc-buildroot-linux-uclibc/sysroot/usr/lib"
if [[ -f $_uclibc_lib/libc.a && ! -f $_sysroot_lib/libc.a ]]; then
  mkdir -p "$_sysroot_lib"
  cp -a "$_uclibc_lib"/*.a "$_sysroot_lib/"
fi

# shellcheck source=/dev/null
source "$SRC/pathsetup.sh"
