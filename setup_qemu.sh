#!/usr/bin/env bash
# Build qemu-ajit (sparc-softmmu) into $AJIT_HOME/build/qemu-ajit-v1.0.
# Source lives at $AJIT_HOME/qemu-ajit-v1.0. Run inside ajit_build_dev after
# source ./set_ajit_home. Does not bake qemu into the Docker image.

set -euo pipefail

if [[ -z "${AJIT_HOME:-}" ]]; then
  echo "setup_qemu.sh: set AJIT_HOME (source ./set_ajit_home)" >&2
  exit 1
fi

_SRC="$AJIT_HOME/qemu-ajit-v1.0"
_OUT="${AJIT_QEMU_BUILD_DIR:-$AJIT_HOME/build/qemu-ajit-v1.0}"
_JOBS="${JOBS:-$(nproc)}"
_TARGET_LIST="${QEMU_TARGET_LIST:-sparc-softmmu}"

if [[ ! -x "$_SRC/configure" ]]; then
  echo "setup_qemu.sh: missing $_SRC/configure" >&2
  exit 1
fi

_install_qemu_host_deps() {
  if command -v ninja >/dev/null 2>&1 && pkg-config --exists glib-2.0 pixman-1 2>/dev/null; then
    return 0
  fi
  echo "setup_qemu.sh: installing qemu host packages"
  if [[ "$(id -u)" -eq 0 ]]; then
    _APT=(apt-get)
  elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    _APT=(sudo apt-get)
  else
    echo "setup_qemu.sh: need root/sudo to apt-get ninja, glib, pixman." >&2
    echo "setup_qemu.sh: as root: apt-get install -y ninja-build pkg-config meson python3-setuptools python3-tomli libglib2.0-dev libpixman-1-dev" >&2
    echo "setup_qemu.sh: or rebuild ajit_base after docker/ajit_base/setup_ajit_base.sh" >&2
    exit 1
  fi
  export DEBIAN_FRONTEND=noninteractive
  "${_APT[@]}" update
  "${_APT[@]}" install -y --no-install-recommends \
    ninja-build \
    pkg-config \
    meson \
    python3-setuptools \
    python3-tomli \
    libglib2.0-dev \
    libpixman-1-dev
}

_install_qemu_host_deps

mkdir -p "$_OUT"
cd "$_OUT"

if [[ ! -f Makefile && ! -f build.ninja ]]; then
  echo "setup_qemu.sh: configuring $_TARGET_LIST -> $_OUT"
  "$_SRC/configure" --target-list="$_TARGET_LIST"
fi

echo "setup_qemu.sh: make -j$_JOBS"
if [[ -f build.ninja ]]; then
  ninja -j"$_JOBS"
else
  make -j"$_JOBS"
fi

if [[ ! -x "$_OUT/qemu-system-sparc" ]]; then
  echo "setup_qemu.sh: expected $_OUT/qemu-system-sparc" >&2
  exit 1
fi

echo "setup_qemu.sh: done"
"$_OUT/qemu-system-sparc" -version | head -1
