#!/usr/bin/env bash
# 16.04 arm64 only: no distro python>=3.6 (CoRTOS uses f-strings). Skip if python3 is already >=3.6.
set -euo pipefail
if command -v python3 >/dev/null 2>&1 \
    && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 6) else 1)'; then
  exit 0
fi
if command -v python3.6 >/dev/null 2>&1; then
  exit 0
fi
if [[ -z "${AJIT_BUILD_DIR:-}" ]]; then
  echo "Need AJIT_BUILD_DIR (source ajit_env)."
  exit 1
fi
prefix="$AJIT_BUILD_DIR/opt/python-3.6"
if [[ -x "$prefix/bin/python3.6" ]]; then
  exit 0
fi
src="$AJIT_BUILD_DIR/src/Python-3.6.15"
tgz="$AJIT_BUILD_DIR/src/Python-3.6.15.tgz"
mkdir -p "$AJIT_BUILD_DIR/src"
if [[ ! -f "$tgz" ]]; then
  wget -O "$tgz" https://www.python.org/ftp/python/3.6.15/Python-3.6.15.tgz
fi
if [[ ! -d "$src" ]]; then
  tar xf "$tgz" -C "$AJIT_BUILD_DIR/src"
fi
cd "$src"
./configure --prefix="$prefix" --without-ensurepip
make -j"$(nproc)"
make install
wget -O /tmp/get-pip36.py https://bootstrap.pypa.io/pip/3.6/get-pip.py
"$prefix/bin/python3.6" /tmp/get-pip36.py
"$prefix/bin/python3.6" -m pip install --no-cache-dir pyelftools pyyaml
