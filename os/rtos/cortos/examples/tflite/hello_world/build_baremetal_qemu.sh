#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export TFLITE_TEST_SRCS="\
tensorflow/lite/micro/examples/hello_world/hello_world_test.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/hello_world/models/hello_world_float_model_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/hello_world/models/hello_world_int8_model_data.cc"
exec "${HERE}/../build_baremetal_qemu.sh" "$@"
