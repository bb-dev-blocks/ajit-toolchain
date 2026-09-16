#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../common.sh
source "${HERE}/../common.sh"
export TFLITE_TEST_SRCS
TFLITE_TEST_SRCS="$(tflite_kernel_srcs)"
exec "${HERE}/../../build_baremetal_qemu.sh" "$@"
